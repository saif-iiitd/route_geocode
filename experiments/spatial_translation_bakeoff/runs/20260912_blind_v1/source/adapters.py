"""Three real providers. Only four-field blind records enter these methods.

No evaluation imports, tool calls, file-search context, example translations, or
provider fallbacks. Exception bodies are never logged (they can contain credentials).
"""
import importlib.util
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from .common import blind_record, dumps
from .schema import SCHEMA, validate_alignment


class ProviderFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def present(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def preflight(system, config):
    blockers = []
    if system == 'openai':
        if not os.getenv('OPENAI_API_KEY'):
            blockers.append('OPENAI_API_KEY_NOT_CONFIGURED')
    elif system == 'google':
        if not present('google.cloud.translate_v3'):
            blockers.append('GOOGLE_CLOUD_TRANSLATE_LIBRARY_NOT_INSTALLED')
        if not config.get('project'):
            blockers.append('GOOGLE_CLOUD_PROJECT_NOT_CONFIGURED')
        adc = Path(os.environ.get('APPDATA', str(Path.home() / '.config'))) / 'gcloud/application_default_credentials.json'
        if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS') and not adc.exists():
            blockers.append('GOOGLE_ADC_NOT_CONFIGURED_ON_THIS_LOCAL_HOST')
    else:
        for module in ('torch', 'transformers', 'IndicTransToolkit', 'sentencepiece'):
            if not present(module):
                blockers.append('MISSING_DEPENDENCY_' + module)
        token_file = Path(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface'))) / 'token'
        if not os.getenv('HF_TOKEN') and not os.getenv('HUGGING_FACE_HUB_TOKEN') and not token_file.exists():
            blockers.append('GATED_MODEL_HF_CREDENTIAL_NOT_CONFIGURED')
        if len(config.get('revision', '')) != 40:
            blockers.append('MODEL_REVISION_NOT_PINNED')
    return blockers


def openai_request(record, config, prompt):
    record = blind_record(record)
    # No tools, conversation state or retrieval: standalone prospective input only.
    return {'model': config['model'], 'instructions': prompt,
            'input': dumps(record), 'store': False,
            'max_output_tokens': config['max_output_tokens'],
            'reasoning': {'effort': config['reasoning_effort']},
            'text': {'format': {'type': 'json_schema', 'name': 'spatial_translation',
                                 'strict': True, 'schema': SCHEMA}}}


class OpenAIArm:
    def __init__(self, config, prompt):
        self.config, self.prompt = config, prompt

    def translate(self, record):
        request = urllib.request.Request('https://api.openai.com/v1/responses',
            data=dumps(openai_request(record, self.config, self.prompt)).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
                request_id = response.headers.get('x-request-id', '')
        except urllib.error.HTTPError as error:
            raise ProviderFailure('HTTP_' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ProviderFailure('NETWORK_OR_TIMEOUT') from None
        if data.get('status') != 'completed':
            raise ProviderFailure('RESPONSE_NOT_COMPLETED')
        content = ''.join(c.get('text', '') for item in data.get('output', [])
                          if item.get('type') == 'message' for c in item.get('content', [])
                          if c.get('type') == 'output_text')
        try:
            alignment = json.loads(content)
            validate_alignment(alignment, record['text_original'])
        except (ValueError, TypeError, KeyError):
            raise ProviderFailure('MALFORMED_STRUCTURED_OUTPUT') from None
        return alignment['translation'], alignment, {
            'actual_model': data.get('model', ''), 'response_id': data.get('id', ''),
            'request_id': request_id, 'usage': data.get('usage'), 'api': 'Responses v1',
            'response_created_at': data.get('created_at'), 'backend_snapshot': 'not guaranteed by alias'}


class GoogleArm:
    def __init__(self, config, prompt):
        from google.cloud import translate_v3
        self.client = translate_v3.TranslationServiceClient()
        self.config = config

    def translate(self, record):
        record = blind_record(record)
        parent = f"projects/{self.config['project']}/locations/{self.config['location']}"
        response = self.client.translate_text(request={
            'parent': parent, 'contents': [record['text_original']],
            'source_language_code': 'hi', 'target_language_code': 'en', 'mime_type': 'text/plain',
            'model': parent + '/models/general/nmt'}, retry=None, timeout=120)
        if len(response.translations) != 1:
            raise ProviderFailure('UNEXPECTED_TRANSLATION_COUNT')
        result = response.translations[0]
        return result.translated_text, None, {
            'actual_model': result.model or 'general/nmt', 'api': 'Cloud Translation Advanced v3',
            'project': self.config['project'], 'location': self.config['location'],
            'source_language': 'hi', 'target_language': 'en', 'glossary': None,
            'backend_revision': 'not exposed by service', 'billable_characters': len(record['text_original'])}


class IndicTrans2Arm:
    def __init__(self, config, prompt):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from IndicTransToolkit.processor import IndicProcessor
        self.torch, self.config = torch, config
        torch.manual_seed(config['seed'])
        torch.use_deterministic_algorithms(True)
        self.device = config['device']
        self.tokenizer = AutoTokenizer.from_pretrained(config['model'], revision=config['revision'],
                                                       trust_remote_code=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(config['model'], revision=config['revision'],
            trust_remote_code=True, attn_implementation='eager', torch_dtype=torch.float32).to(self.device).eval()
        self.processor = IndicProcessor(inference=True)

    def translate(self, record):
        record = blind_record(record)
        source = self.processor.preprocess_batch([record['text_original']], src_lang='hin_Deva', tgt_lang='eng_Latn')
        tokens = self.tokenizer(source, return_tensors='pt', padding=True, truncation=False).to(self.device)
        if tokens['input_ids'].shape[-1] > self.config['max_source_tokens']:
            raise ProviderFailure('SOURCE_TOO_LONG_NO_SILENT_TRUNCATION')
        with self.torch.inference_mode():
            generated = self.model.generate(**tokens, do_sample=False, num_beams=self.config['num_beams'],
                max_new_tokens=self.config['max_new_tokens'], num_return_sequences=1)
        if generated.shape[-1] >= self.config['max_new_tokens'] and generated[0, -1].item() != self.tokenizer.eos_token_id:
            raise ProviderFailure('OUTPUT_TOKEN_LIMIT')
        decoded = self.tokenizer.batch_decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=True)
        translated = self.processor.postprocess_batch(decoded, lang='eng_Latn')[0]
        return translated, None, {'actual_model': self.config['model'], 'revision': self.config['revision'],
            'device': self.device, 'torch_version': self.torch.__version__, 'seed': self.config['seed'],
            'decoding': 'beam search, no sampling; reproducibility limited to pinned environment/hardware'}


ARMS = {'openai': OpenAIArm, 'google': GoogleArm, 'indictrans2': IndicTrans2Arm}
