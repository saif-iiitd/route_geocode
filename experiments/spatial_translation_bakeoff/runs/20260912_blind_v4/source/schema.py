"""Strict output contract; structural validity is not semantic correctness."""


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


STRING = {'type': 'string'}
INTEGER = {'type': 'integer'}
BOOLEAN = {'type': 'boolean'}
MENTION = obj({'original_surface': STRING, 'english_surface': STRING,
               'mention_order': INTEGER, 'feature_type': STRING, 'uncertain': BOOLEAN})
RELATION = obj({'relation': STRING, 'source_mention_order': {'type': ['integer', 'null']},
                'target_mention_order': {'type': ['integer', 'null']}, 'uncertain': BOOLEAN})
SCHEMA = obj({'translation': STRING, 'place_mentions': {'type': 'array', 'items': MENTION},
              'spatial_relations': {'type': 'array', 'items': RELATION}, 'route_clause_count': INTEGER,
              'translation_uncertainties': {'type': 'array', 'items': STRING}})


def validate_schema(value, schema=SCHEMA):
    types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    kind = 'null' if value is None else {str: 'string', int: 'integer', bool: 'boolean', list: 'array', dict: 'object'}.get(type(value))
    if kind not in types:
        raise ValueError('Structured output type mismatch')
    if kind == 'object':
        if set(value) != set(schema['required']):
            raise ValueError('Structured output fields mismatch')
        for k, v in value.items():
            validate_schema(v, schema['properties'][k])
    if kind == 'array':
        for v in value:
            validate_schema(v, schema['items'])


def validate_alignment(value, original):
    validate_schema(value)
    if not value['translation'].strip() or value['route_clause_count'] < 0:
        raise ValueError('Empty translation or invalid clause count')
    end = 0
    for n, mention in enumerate(value['place_mentions'], 1):
        surface = mention['original_surface']
        start = original.find(surface, end) if surface else -1
        if start < 0 or mention['mention_order'] != n or not mention['english_surface'].strip():
            raise ValueError('Invalid original mention alignment/order')
        end = start + len(surface)
    for relation in value['spatial_relations']:
        for key in ('source_mention_order', 'target_mention_order'):
            ref = relation[key]
            if ref is not None and not 1 <= ref <= len(value['place_mentions']):
                raise ValueError('Relation references nonexistent mention')
