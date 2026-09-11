"""Deterministic provenance screening, not a replacement semantic parser.

Reads source files only. No model inference, geocoding, translation or network.
Outputs a per-record review ledger plus aggregate evidence under results/.
The bounded bilingual glossary is a screening aid, not complete NER.
"""
import csv, json, re, html, unicodedata, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/provenance_audit'
csv.field_size_limit(10000000)

def load(path):
    with path.open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))
def folded(s):
    return unicodedata.normalize('NFD', s).replace('\u093c','').casefold()
def base(s):
    s = html.unescape(s)
    s = re.sub(r'(?i)traffic\s*alert\s*[:.!-]?', ' ', s)
    s = re.sub(r'https?://\S+|pic\.twitter\.com/\S+', ' ', s)
    return re.sub(r'[^\w]', '', s.casefold())
def letters(s): return re.sub(r'[^a-z0-9]', '', s.casefold())

# Each line: canonical label | Hindi pattern | acceptable Latin aliases.
# Deliberately constrained; lack of a match is not proof of mistranslation.
GLOSSARY = r'''
Chirag Delhi|चिराग\s*दिल्ली|chirag delhi
Outer Ring Road|(?:आउटर|बाहरी)\s*रिंग\s*रो[डड़]|outer ring road;external ring road
Ring Road|रिंग\s*रो[डड़]|ring road
Palika Place|पालिका\s*प्लेस|palika place
Patel Chowk|पटेल\s*चौक|patel chowk
Lajpat Nagar|लाजपत\s*नगर|lajpat nagar
Shyamlal College|श्यामलाल\s*कॉलेज|shyamlal college;shyam lal college
Bihari Colony|बिहारी\s*(?:कालोनी|कॉलोनी)|bihari colony
Dhaula Kuan|धौला\s*कु[आअ][ँं]?|dhaula kuan;dhoula kuan
Azad Market|आ[जज़]ाद\s*मार्क[ेि]ट|azad market;azad market chowk
Azadpur|आ[जज़]ादपुर|azadpur
Nehru Place|नेह[ररु]+[ुू]?\s*प्लेस|nehru place;neharu place
Moolchand|मूलच[ंन]द|moolchand;mulchand
Lala Lajpat Rai Marg|लाला\s*लाजपत\s*राय\s*मार्ग|lala lajpat rai marg;lala lajpat rai road;lala lajpat rai route
Rani Jhansi Road|रानी\s*झा[ँं]?सी\s*रो[डड़]|rani jhansi road
Connaught Place|(?:कनाट|क्नॉट|कनॉट|क्नाट)\s*प्लेस|connaught place;conaught place;cunat place;conat place
Outer Circle|आउटर\s*सर्किल|outer circle
Savitri Cinema|स[ाव]व?ि?त्रि?\s*सिनेमा|savitri cinema
Greater Kailash|ग्रेटर\s*कैलाश|greater kailash
Pusa|पूसा|pusa
Moti Nagar|मोती\s*नगर|moti nagar
Moti Bagh|मोती\s*बा[गघ]|moti bagh;moti bag
Wazirabad|व[जज़]ी?राबाद|wazirabad;wajirabad
Yamuna Vihar|यमुना\s*विहार|yamuna vihar
Khajuri|ख[जज़]ु?री|khajuri;khajoori
Gurgaon|गु[डड़][गग़]ा[ँं]?व|gurgaon;gurugram
Gurugram|गुरुग्राम|gurugram;gurgaon
Ashram|आश्रम|ashram
Lado Sarai|ल[ाड़डो]+\s*सराय|lado sarai;ladho sarai;laro sarai
Rao Tula Ram Marg|राव\s*तुला\s*राम\s*मार्ग|rao tula ram marg;rao tula ram road;rtr marg
Adchini|अध?चि?नी|adchini;adhichini
Vasant Vihar|वसंत\s*विहार|vasant vihar;basant vihar
Ajmeri Gate|अजमेरी\s*गेट|ajmeri gate;ajmeri gate
Paharganj|पहा[डड़]?गंज|paharganj;pahar ganj
Panchsheel|पंचशील|panchsheel
Filmistan|फिल्मिस्तान|filmistan;filmistaan
Shanti Van|शांति\s*वन|shanti van;shantivan;santhawan
Talkatora|तालकटोरा|talkatora;taalkatora;taalkota
Shankar Road|शंकर\s*रो[डड़]|shankar road
Park Street|पार्क\s*स्ट्रीट|park street
Khanpur|खानपुर|khanpur
Sainik Farm|सैनिक\s*फार्म|sainik farm
Kapashera|कापसहे[डड़]ा|kapashera;kapashera
Rajokri|र[जज़][ौो]क[रड़]ी|rajokri;rajokari;rajukari;rajokro
Dilshad Garden|दिलशाद\s*गार्डन|dilshad garden
Timarpur|तिमारपुर|timarpur
Sapna Cinema|सपना\s*सिनेमा|sapna cinema
Raja Garden|राजा\s*गार्डन|raja garden
East of Kailash|ईस्ट\s*ऑ[फ़फ]\s*कैलाश|east of kailash
Munirka|मुनिरका|munirka
Dwarka|द्वारका|dwarka
Okhla Mod|ओखला\s*मो[डड़]|okhla mod;okhla mor;okhla turn
Badarpur|बदरपुर|badarpur
Pul Prahladpur|पुल\s*प्र[हह्]*लाद\s*पुर|pul prahladpur;pul prahlad pur;prahladpur;prahlad pur
Mahipalpur|महिपालपुर|mahipalpur;mhipalpur
Naraina|नारायणा|naraina;narayana
Aurobindo|अर[बव]िंदो|aurobindo;arobindo;arvindo
Maharani Bagh|महारानी\s*बा[गघ]|maharani bagh;maharani bag
Andheria Mod|अंधेरिया\s*मो[डड़]|andheria mod;andheriya mod;andheriya mode;andheria mor
Masoodpur|मसूदपुर|masoodpur;masudpur
Rajdoot Hotel|राजदूत\s*होटल|rajdoot hotel
Mathura Road|मथुरा\s*रो[डड़]|mathura road
Hauz Khas|हौ[जज़]\s*खास|hauz khas;hauz khash
Loha Mandi|लोहा\s*मंडी|loha mandi
Samrat Hotel|सम्राट\s*होटल|samrat hotel
Kasturba Gandhi Marg|कस्तूरबा\s*गा[ँं]?धी\s*मार्ग|kasturba gandhi marg;kasturba gandhi road
Desh Bandhu Gupta Road|देश\s*ब[ंन]धु\s*गुप्ता\s*रो[डड़]|desh bandhu gupta road;deshbandhu gupta road
Uttam Nagar|उत्तम\s*नगर|uttam nagar
Rajouri Garden|राजौरी\s*गार्डन|rajouri garden;rajuri garden
Mayapuri|मायापुरी|mayapuri;maya puri
Sarai Kale Khan|सराय\s*काले\s*खा[नंँ]|sarai kale khan;sarai kala khan;sarai kale kha
Akshardham|अक्षरधाम|akshardham;akshar dham
Pankha Road|पंखा\s*रो[डड़]|pankha road
Khan Market|खान\s*मार्केट|khan market
Delhi Cantt|दिल्ली\s*क[ेै]ं?ट|delhi cantt;delhi cantonment;delhi kent
Palam|पालम|palam
Narela|नरेला|narela;narail
Bawana|बवाना|bawana
Jasola Road|जसोला\s*रो[डड़]|jasola road
Shaheen Bagh|(?:शाहीन|शाहींन|साइन)\s*बा[गघ]|shaheen bagh;shahin bagh;shine bhah
Kanjhawala|कंझावला|kanjhawala;kanjhawla
Yusuf Sarai|युसु[फफ़]\s*सराय|yusuf sarai;yasuf sarai
Loni|लोनी|loni;looney
Shantipath|शांतिपथ|shantipath;shanti path
Jagatpuri|जगतपुरी|jagatpuri
Karkardooma|क[डड़]क[डड़]डूमा|karkardooma;karkarduma
Sansad Marg|संसद\s*मार्ग|sansad marg;parliament street;parliament road;parliament marg
Chhatta Rail|छत्ता?\s*रेल|chhatta rail;chhata rail;chatta rail;chhatha rail;chhota rail
Baraf Khana|बर्?[फफ़]\s*खाना|baraf khana;barf khana;barafkhana
Peeragarhi|पीराग[ढढ़]ी|peeragarhi;peeragari;peera garhi;piragarhi
Madhuban Chowk|मधुबन\s*चौक|madhuban chowk
Mukarba Chowk|मुकरबा\s*चौक|mukarba chowk
Kamla Nehru College|कमला\s*नेहरु?\s*कॉलेज|kamla nehru college;kamala nehru college
Surajkund|सूरजकुंड|surajkund
Shadipur|शादीपुर|shadipur;shadipur
Rohtak Road|रोहतक\s*रो[डड़]|rohtak road
Noida|न[ोॉ]एडा|noida
SP Mukherjee Marg|एस\s*पी\s*मुखर्जी\s*मार्ग|sp mukherjee marg;s p mukherjee marg
Delhi Gate|दिल्ली\s*गेट|delhi gate
Najafgarh|नजफग[ढढ़]|najafgarh;najaf garh
Nangloi|नांगलोई|nangloi
Rafi Marg|र[फफ़]ी\s*मार्ग|rafi marg;raffi marg
Windsor Place|विंडसर\s*प्लेस|windsor place
Baba Kharak Singh Marg|बाबा\s*ख[डड़]क\s*सिंह\s*मार्ग|baba kharak singh marg;baba khadak singh marg;baba khadak singh route
Kashmiri Gate|कश्मीरी\s*गेट|kashmiri gate;kashmere gate
Yamuna Bazar|यमुना\s*बा[जज़]ा?र|yamuna bazar;yamuna bazaar
Kela Ghat|केला\s*घाट|kela ghat
Hanuman Setu|हनुमान\s*सेतु|hanuman setu
Kalkaji|कालकाजी|kalkaji
Hanuman Mandir|हनुमान\s*मंदिर|hanuman mandir;hanuman temple
India Gate|इंडिया\s*गेट|india gate
Purana Qila|पुराना\s*किला|purana qila;purana kila;old fort
Sher Shah Road|शेरशाह\s*रो[डड़]|sher shah road;shershah road
GPO|जी[.\s]*पी[.\s]*ओ|gpo;general post office
Tilak Nagar|तिलक\s*नगर|tilak nagar
Jail Road|जेल\s*रो[डड़]|jail road
Hari Nagar|हरी?\s*नगर|hari nagar
Ashoka Road|अशोक[ा]?\s*रो[डड़]|ashoka road;ashok road
Feroz Shah Road|फिरोजशाह\s*रो[डड़]|feroz shah road;ferozeshah road
Mandir Marg|मंदिर\s*मार्ग|mandir marg
Patel Nagar|पटेल\s*नगर|patel nagar
'''
LEX = []
for line in GLOSSARY.strip().splitlines():
    label, pat, aliases = line.split('|') if line.count('|') == 2 else (None,None,None)
    # Regex alternatives themselves contain '|': delimiter is the first and last pipe.
    if label is None:
        label, rest = line.split('|',1); pat, aliases = rest.rsplit('|',1)
    LEX.append((label,re.compile(r'(?<![\u0900-\u097f])(?:'+folded(pat)+r')(?![\u0900-\u097f])'),[letters(a) for a in aliases.split(';')]))

# Explicitly inspected cases. These are audit annotations, not source corrections.
MANUAL = {
2:('severe','PLACE_SUBSTITUTION','Jail Road replaced by Tilak Nagar in an English input; method/author unknown.'),
3:('benign','PUNCTUATION_ONLY','R.K Puram -> R.K. Puram; Keshav Puram is separate legacy metadata.'),
4:('severe','TOPONYM_LOSS;DIRECTION_LOSS','GPO destination becomes P.O.; direction towards GPO is lost.'),
5:('possible','RELATION_LOSS','Near Lajpat Nagar police station becomes traffic at the police station.'),
6:('severe','ORIGIN_RELATION_LOSS','Shyamlal College from-origin relationship is missing.'),
7:('severe','PROPER_NAME_LITERAL_TRANSLATION;DIRECTION_LOSS','Palika Place becomes municipality; from/towards relations weakened.'),
8:('equivalent','BILINGUAL_EQUIVALENT','Shyamlal College to Bihari Colony, Road 57 retained.'),
9:('equivalent','BILINGUAL_EQUIVALENT','Lajpat Nagar police station and in-front-of relation retained.'),
14:('severe','TOPONYM_TRANSFORMATION;RELATION_CHANGE','GPO fragmented to Got/P.O.; Ashoka Road relation restructured.'),
17:('equivalent','BILINGUAL_EQUIVALENT','Ashoka Road, Ferozeshah Road, Connaught Place retained.'),
18:('equivalent','BILINGUAL_EQUIVALENT','New Delhi to Moolchand along Lala Lajpat Rai Marg retained semantically.'),
30:('benign','ALIAS_EXPANSION','Delhi Cantt expanded to Delhi Cantonment.'),
35:('possible','ORIGIN_RELATION_LOSS','From Azad Market towards Idgah becomes an unbound Idgah side expression.'),
65:('severe','PLACE_SUBSTITUTION','Bara Tooti Chowk becomes Barabati Chowk.'),
81:('severe','TOPONYM_QUALIFIER_LOSS','Outer Ring Road becomes Ring Road.'),
85:('benign','SPELLING_NORMALIZATION','Shine Bhah to Shaheen Bagh is a plausible spelling correction; retain original surface.'),
86:('benign','SPELLING_NORMALIZATION','Shine Bhah to Shaheen Bagh is a plausible spelling correction; retain original surface.'),
94:('severe','FEATURE_TYPE_CHANGE;DIRECTION_LOSS','Pusa roundabout becomes round-the-clock; from/to relation lost.'),
101:('possible','TOPONYM_ADDITION','Sanjay T-point flyover gains colony; specificity changes without provenance.'),
116:('benign','ALIAS_TRANSLATION','Red Fort to Lal Quila; same landmark alias, no new location inferred.'),
125:('benign','ALIAS_TRANSLATION','Red Fort to Lal Quila; same landmark alias.'),
130:('benign','ALIAS_TRANSLATION','Red Fort to Lal Quila; same landmark alias.'),
136:('corrupt','ORIGINAL_CELL_CORRUPTION;PREVIOUS_ROW_TRANSLATION_COPY','Original is #NAME?; public status is ISBT towards Shastri Park, matching legacy locations. Translated text exactly duplicates previous row 135 Ashoka Road/Patel Chowk tweet. Local copy/alignment contamination; editing mechanism unknown.'),
143:('equivalent','IMPLICIT_LOCATIVE','Rani Jhansi Road traffic normal preserves place despite omitting on.'),
144:('equivalent','FEATURE_SYNONYM','Marg becomes Road; Lala Lajpat Rai identity retained.'),
150:('severe','PROPER_NAME_LITERAL_TRANSLATION;DIRECTION_CHANGE','Chirag becomes lamp; from-source moves to Sadik Nagar in English wording.'),
151:('severe','ROLE_REASSIGNMENT','AIIMS to IIT route and diversion towards Katwaria Sarai are reattached.'),
152:('severe','PROPER_NAME_LITERAL_TRANSLATION;ORIGIN_RELATION_LOSS','Lado Sarai becomes Fight ... Sarai Road.'),
155:('severe','FEATURE_TYPE_LOSS;ROLE_REASSIGNMENT','Rao Tula Ram Marg loses Marg; removal of tree is reversed into removal of Rao Tula Ram.'),
157:('severe','TOPONYM_LOSS','Adchini is replaced by water purifier; diversion origin disappears.'),
168:('severe','PLACE_SUBSTITUTION;RELATION_CHANGE','Sainik Farm becomes Sarkari Farm; Khanpur from-origin attachment changes.'),
183:('severe','PROPER_NAME_LITERAL_TRANSLATION','Sapna Cinema becomes Dream Cinema.'),
184:('severe','PROPER_NAME_LITERAL_TRANSLATION','Raja Garden becomes King Garden.'),
185:('severe','PLACE_SUBSTITUTION','Shanti Van becomes Shanti Man.'),
189:('severe','PROPER_NAME_LITERAL_TRANSLATION','Western Patel Nagar becomes Western Patel city.'),
191:('severe','TOPONYM_LOSS','Okhla Mod becomes right turn, losing named junction.'),
192:('severe','TOPONYM_LOSS','Pul Prahladpur disappears into generic Bridges/Red Light wording.'),
196:('equivalent','BILINGUAL_EQUIVALENT','Naraina to Dhaula Kuan retained.'),
208:('severe','BETWEEN_RELATION_LOSS','Between Aurobindo Chowk and Tughlaq Road becomes a list.'),
209:('equivalent','BILINGUAL_EQUIVALENT','Between Aurobindo Chowk and Tughlaq Road retained.'),
213:('severe','LOCATION_MERGE','Maharani Bagh to Ashram becomes Maharani Bagh Ashram.'),
214:('severe','LANDMARK_ROLE_CHANGE','Near Masoodpur village becomes traffic to Masoodpur village.'),
216:('equivalent','BILINGUAL_EQUIVALENT','Gurgaon to Dhaula Kuan retained.'),
217:('severe','PROPER_NAME_LITERAL_TRANSLATION','Rajdoot Hotel becomes Ambassador Hotel.'),
225:('severe','PROPER_NAME_LITERAL_TRANSLATION','Loha Mandi becomes Iron Maiden.'),
226:('severe','PROPER_NAME_LITERAL_TRANSLATION;FEATURE_TYPE_CHANGE','Samrat Hotel becomes Emperor Hotel; roundabout becomes Round Trip.'),
246:('severe','PROPER_NAME_LITERAL_TRANSLATION','Desh Bandhu Gupta Road becomes country Bundu Gupta Road.'),
257:('severe','DIRECTION_LOSS','Ashram towards Sarai Kale Khan becomes bus on Sarai Kale Khan.'),
260:('equivalent','BILINGUAL_EQUIVALENT','Chirag Delhi to Nehru Place retained.'),
271:('severe','PLACE_ADDITION;TOPONYM_TRANSFORMATION','Delhi Cantt becomes Delhi from Kentucky; a spurious place is introduced.'),
288:('severe','DIRECTION_REVERSAL;TOPONYM_TRANSFORMATION','Jasola Road from-origin and Sain Bagh destination reverse; Bagh name garbled.'),
290:('severe','DIRECTION_REVERSAL;TOPONYM_TRANSFORMATION','Same reversal and garbling as row 288.'),
306:('equivalent','BILINGUAL_EQUIVALENT','Gandhi Nagar Main Market retained.'),
309:('equivalent','BILINGUAL_EQUIVALENT','Near Wazirpur depot retained.'),
313:('equivalent','BILINGUAL_EQUIVALENT','Between Khanpur and Saket Metro retained.'),
319:('equivalent','BILINGUAL_EQUIVALENT','Dhaula Kuan to Barar Square retained.'),
322:('severe','PLACE_SUBSTITUTION','Shantipath Marg becomes Shanti Marg.'),
327:('severe','DIRECTION_REVERSAL','ITO se Karkari Mor becomes ITO from Karkari Mor.'),
333:('possible','TOPONYM_ADDITION','Chandgi Ram Akhara gains Master and canonical spelling; provenance unknown.'),
373:('severe','ROAD_TO_BUILDING','Sansad Marg becomes Parliament without the street/road designation.'),
382:('equivalent','BILINGUAL_EQUIVALENT','Near Mayapuri flyover retained.'),
393:('severe','TOPONYM_LOSS;PROPER_NAME_LITERAL_TRANSLATION','Baraf Khana Chowk disappears into ice/choke wording.'),
409:('severe','DIRECTION_LOSS;TOPONYM_TRANSFORMATION','Peeragarhi to Madhuban Chowk becomes Peabagari ... Madhuban Chowk without from/to.'),
426:('equivalent','BILINGUAL_EQUIVALENT','Under Shadipur Metro station retained.'),
431:('severe','TOPONYM_LOSS','Pul Prahladpur omitted.'),
461:('severe','PROPER_NAME_LITERAL_TRANSLATION','Baraf Khana Chowk becomes ice khan chowk.'),
481:('severe','PLACE_SUBSTITUTION','SP Mukherjee Marg becomes SDM Mukherjee Marg.'),
494:('severe','DIRECTION_REVERSAL','Delhi to Noida becomes Noida to Delhi.'),
539:('severe','PROPER_NAME_LITERAL_TRANSLATION;INCONSISTENT_REPEAT','Azad Market retained once but another occurrence becomes free market.'),
603:('severe','PROPER_NAME_LITERAL_TRANSLATION','Baraf Khana becomes snow-fed food.'),
642:('severe','TOPONYM_LOSS','Rafi Marg origin omitted.'),
647:('severe','TOPONYM_SUBSTITUTION','Outer Circle becomes Interior Circle Circle.'),
656:('possible','TOPONYM_ADDITION','Chandgi Ram Akhara gains Master and canonical spelling; provenance unknown.'),
661:('severe','PROPER_NAME_LITERAL_TRANSLATION;TOPONYM_LOSS','Baraf Khana becomes Ice Cliff Chowk and repeated destination is omitted.'),
699:('severe','PROPER_NAME_LITERAL_TRANSLATION','Baraf Khana and Azad Market become ice-food and free market.'),
727:('equivalent','BILINGUAL_EQUIVALENT','Starting from Gurudwara Shishganj is retained; आरम्भ होकर is an origin expression, not via.'),
851:('severe','DIRECTION_REVERSAL;TOPONYM_TRANSFORMATION','Moti Nagar to Inder Lok becomes Indira Lok to Moti Nagar.'),
917:('severe','TOPONYM_LOSS','Pahari Dhiraj destination becomes hill hill.'),
1012:('equivalent','UNTRANSLATED_HINDI','Original spatial wording retained in Hindi; not suitable for current English-only regex parser.'),
1170:('severe','PROPER_NAME_SPLIT','Chirag Delhi becomes Chirag traffic from Delhi; origin identity is fragmented.'),
1183:('severe','PROPER_NAME_LITERAL_TRANSLATION','Azad Market, Baraf Khana and Tis Hazari become free market, Ice Catering and Thirty Hazari.'),
1204:('severe','PROPER_NAME_LITERAL_TRANSLATION','Azad Market, Baraf Khana and Rani Jhansi become free market, Ice Catering and Queen Jhansi.'),
1216:('equivalent','BILINGUAL_EQUIVALENT','Kalindi Kunj to Noida retained.'),
1293:('severe','TOPONYM_LOSS','Rawta Mod location is omitted from translation.'),
1476:('equivalent','BILINGUAL_EQUIVALENT','Deepali Chowk to Madhuban Chowk, before Madhuban underpass retained.'),
1669:('equivalent','BILINGUAL_EQUIVALENT','Mathura Road, C-Hexagon, Bhairon Marg/Road and Rajpath retained.'),
1780:('severe','TIME_TO_LOCATION_CONTAMINATION','5 pm to 8 pm becomes vehicles from Sector 8 and 5, blending time and place.'),
2031:('severe','PROPER_NAME_LITERAL_TRANSLATION','Azad Market retained once but free market replaces the second mention.'),
2071:('severe','FEATURE_TYPE_CHANGE','Jaswant Singh roundabout becomes round-trip.'),
2290:('equivalent','BILINGUAL_EQUIVALENT','Mithapur to Faridabad and use Mathura Road retained.'),
2302:('severe','PROPER_NAME_LITERAL_TRANSLATION','Baraf Khana becomes Ice Catering and ice-cold.'),
2496:('severe','ORIGIN_LOSS;VERTICAL_RELATION_CHANGE','Hyatt origin omitted; vehicles going below bridge becomes work under HTV/LGV bridge.'),
2635:('corrupt','SOURCE_FIELD_SPILL;MISSING_IDENTIFIER','Sher Shah Road appears in geo and continuation in mentions; original truncated. Preserve all cells without reconstructing tweet.'),
2675:('severe','TOPONYM_SPLIT','Hauz Khas becomes Hauz, especially; source-origin relation weakened.'),
2783:('severe','ROLE_REASSIGNMENT','Munirka to airport and Moti Bagh to airport become a route from Moti Bagh to Munirka.'),
2798:('severe','PROPER_NAME_LITERAL_TRANSLATION','Raja Garden flyover becomes King Garden flyover.'),
2820:('severe','TOPONYM_LOSS;DIRECTION_LOSS','Mundka destination omitted; Nangloi origin is garbled as Nandlaoi.'),
2860:('severe','DIRECTION_REVERSAL;VIA_ROLE_CHANGE','NH8 via Dhaula Kuan to Ramlila Maidan becomes from Ramlila Ground to NH8 from Dhaula Kua.'),
3176:('severe','TOPONYM_MENTION_LOSS;VIA_ROLE_LOSS','Return leg via Modi flyover is lost; the flyover is preserved only in the outbound leg.'),
3221:('equivalent','BILINGUAL_EQUIVALENT','Uttam Nagar to Tilak Nagar, near Ganesh Nagar red light retained.'),
3486:('equivalent','BILINGUAL_EQUIVALENT','Bhorgarh to Alipur retained.'),
3555:('equivalent','BILINGUAL_EQUIVALENT','Captain Gaur Marg/Road, in front of Okhla Mandi gate 1 retained.'),
3684:('severe','PROPER_NAME_LITERAL_TRANSLATION','Lal Kuan becomes Red Kuan.'),
3693:('severe','PROPER_NAME_LITERAL_TRANSLATION','Lal Kuan becomes Red Kuan.'),
3746:('severe','TOPONYM_LOSS;ACRONYM_CORRUPTION','Modi Mill flyover omitted; I P flyover becomes I fly flyover.'),
3875:('severe','TOPONYM_ACRONYM_CHANGE','ILBS Hospital becomes ILS Hospital.'),
4097:('equivalent','BILINGUAL_EQUIVALENT','Nehru Place to Sant Nagar, in front of Nehru Place bus stand retained.'),
4153:('severe','ROUTE_STATUS_REVERSAL','Maharani Bagh to Sarai Kale Khan now reopened becomes now closed.'),
4551:('severe','VIA_ROLE_CHANGE','Via Nizamuddin flyover on a Noida-to-ITO journey becomes a to-Nizamuddin-flyover instruction.'),
4614:('equivalent','BILINGUAL_EQUIVALENT','MB Road to Mehrauli, near Khanpur retained.'),
4755:('equivalent','BILINGUAL_EQUIVALENT','Satyawati College to Keshav Puram on Chaudhary Gulab Singh Road retained.'),
4816:('severe','TOPONYM_LOSS;PROPER_NAME_LITERAL_TRANSLATION','Pragati Maidan gate 2 becomes Progress/Road Traffic Ground; Bhairon Marg fragmented.'),
4863:('severe','TOPONYM_TRANSFORMATION','Maharashtra Bhavan becomes Maha Bhavan.'),
4937:('equivalent','BILINGUAL_EQUIVALENT','Anand Vihar railway station new entry gate retained.'),
4978:('severe','DIRECTION_LOSS','From Subramaniam Bharati Marg towards Zakir Hussain Marg becomes a list.'),
5021:('severe','DIRECTION_REVERSAL;TOPONYM_TRANSFORMATION','Mathura Road to Purana Qila Road becomes Old Math Road to Mathura Road.'),
5075:('possible','BETWEEN_ATTACHMENT_CHANGE','Between two Najafgarh bus stands becomes between Najafgarh; ambiguous endpoint attachment.'),
5076:('severe','PROPER_NAME_LITERAL_TRANSLATION','Raja Garden flyover becomes King Garden flyover.'),
5101:('severe','DIRECTION_REVERSAL;TOPONYM_TRANSFORMATION','Idgah to Tis Hazari becomes Thane Hazar to Idgah.'),
5110:('severe','TOPONYM_TRANSFORMATION;DIRECTION_CHANGE','Tis Hazari becomes Thane to Hazari, introducing an apparent extra place and route.'),
5144:('severe','PLACE_SUBSTITUTION','Chirag Delhi becomes Delhi Delhi.'),
5145:('severe','PLACE_SUBSTITUTION','Kela Ghat becomes Kala Ghat.'),
}

def mentions(text):
    t = folded(text); ans=[]
    for label,pat,aliases in LEX:
        for m in pat.finditer(t): ans.append((m.start(),m.end(),label,m.group(),aliases))
    # Prefer the longest overlapping mention, e.g. Outer Ring Road over Ring Road.
    selected=[]
    for x in sorted(ans,key=lambda x: (-(x[1]-x[0]),x[0])):
        if not any(x[0]<y[1] and y[0]<x[1] for y in selected):selected.append(x)
    return sorted(selected)

def latin_terms(text, terms):
    return [m.group() for m in terms.finditer(text)]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=load(ROOT/'Data/tweets_data.csv'); routes=load(ROOT/'Data/routes_data.csv')
    wordlist=sorted({t.strip() for t in (ROOT/'Data/tweet_location_terms.txt').read_text(encoding='utf-8').splitlines() if t.strip()},key=lambda s:(-len(s),s))
    terms=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(t) for t in wordlist)+r')(?!\w)',re.I)
    results=[]
    for rn,row in enumerate(rows,2):
        a,b=row['text'],row['translated_text']; af=folded(a); bf=letters(b)
        hindi=bool(re.search('[\u0900-\u097f]',a)); known=mentions(a)
        missing=[x[2] for x in known if not any(z in bf for z in x[4])]
        lost_count=[]
        for label in dict.fromkeys(x[2] for x in known):
            ms=[x for x in known if x[2]==label];n=sum(bf.count(z) for z in set(ms[0][4]))
            if n and n<len(ms):lost_count.append(label)
        relation=[]
        if hindi:
            # Only check from after a recognized place, not arbitrary causal 'se'.
            origin=any(re.match(r'\s*(?:चौक|मार्ग|रोड|फ्लाईओवर|मेट्रो\s*स्टेशन)?\s*से(?![\u0900-\u097f])',af[x[1]:]) for x in known)
            if origin and not re.search(r'\bfrom\b',b,re.I):relation.append('EXPLICIT_FROM_NOT_PRESERVED')
            if re.search(r'की\s*(?:तरफ|ओर)|के\s*(?:बीच|बिच)|के\s*पास|होते\s*हुए|होकर',af):
                for pat,en,label in [
                    (r'की\s*(?:तरफ|ओर)',r'\b(?:to|towards|toward|side|direction)\b','DIRECTION_CUE_NOT_PRESERVED'),
                    (r'के\s*(?:बीच|बिच)',r'\bbetween\b','BETWEEN_NOT_PRESERVED'),
                    (r'के\s*पास',r'\b(?:near|nearby|close|beside|adjacent)\b','NEAR_NOT_PRESERVED'),
                    (r'होते\s*हुए|(?<!आरम्भ )(?<!शुरू )(?<!शुरु )होकर',r'\b(?:via|through|using|along|by)\b','VIA_NOT_PRESERVED')]:
                    if re.search(pat,af) and not re.search(en,b,re.I):relation.append(label)
            # Vertical relations often distinguish an underpass from an overpass.
            if re.search(r'के\s*नीचे',af) and not re.search(r'\b(?:under|underneath|below|beneath)\b',b,re.I):relation.append('UNDER_NOT_PRESERVED')
        else:
            aa=re.findall(r'\b(?:from|to|towards|via|on|near|between|under|along)\b',a,re.I)
            bb=re.findall(r'\b(?:from|to|towards|via|on|near|between|under|along)\b',b,re.I)
            if [x.lower() for x in aa]!=[x.lower() for x in bb]:relation.append('ENGLISH_RELATION_SEQUENCE_CHANGE')
        ma=MANUAL.get(rn); exact=a==b; benign=base(a)==base(b)
        tags=[];possible_name=bool(missing or lost_count);possible_relation=bool(relation)
        if not hindi and not benign:
            # All 31 such English/non-Hindi cases have been inspected. Only three
            # retain uncertainty about added toponym specificity, plus row 2.
            possible_name=rn in {2,101,333,656}
        if ma:
            level,tag,note=ma;tags=tag.split(';')
            if level in ('benign','equivalent'):
                possible_name=False;possible_relation=False;missing=[];lost_count=[];relation=[]
            elif level=='corrupt':possible_name=False;possible_relation=False
            elif level=='severe':
                possible_name |= any(s in tag for s in ['TOPONYM','PLACE_','PROPER_NAME','FEATURE_TYPE','ROAD_TO','LOCATION_MERGE'])
                possible_relation |= any(s in tag for s in ['DIRECTION','RELATION','ROLE_','LOCATION_MERGE'])
        else:level=note=''
        # The remaining non-Hindi edited cases were inspected as spelling,
        # alias or nonspatial edits; no additional location is asserted.
        if not hindi and not benign and not ma:
            level='benign';note='Inspected: spelling/alias expansion or nonspatial wording; spatial identity appears unchanged.'
        if level=='corrupt':category='SOURCE_DATA_CORRUPTION'
        elif level=='severe':category='SEVERE_SPATIAL_DISCREPANCY'
        elif exact:category='IDENTICAL_TEXT'
        elif benign or level in ('benign','equivalent'):category='BENIGN_TEXTUAL_DIFFERENCE'
        elif possible_name:category='POSSIBLE_TOPONYM_CHANGE'
        elif possible_relation:category='POSSIBLE_SPATIAL_RELATION_CHANGE'
        else:category='UNRESOLVED_CROSS_LANGUAGE'
        needs=category not in ('IDENTICAL_TEXT','BENIGN_TEXTUAL_DIFFERENCE')
        sid=re.search(r'/status/(\d+)',row['permalink'])
        orig_names=latin_terms(a,terms)
        target_names=latin_terms(b,terms)
        possible=possible_name or possible_relation or level=='severe'
        results.append(dict(dataset_row=rn,source_row_key=row['Unnamed: 0'],tweet_id=sid.group(1) if sid else '',dataset_id_raw=row['id'],tweet_url=row['permalink'],
            language_recorded=row['detected_lang'],original_has_devanagari=hindi,text_original=a,text_translated=b,text_for_current_parser=b,
            audit_class=category,possible_spatial_meaning_change=possible,possible_toponym_change=possible_name,possible_spatial_relation_change=possible_relation,
            severe_inspected=level=='severe',requires_manual_inspection=needs,review_level=level or 'automated_screen',review_note=note,
            discrepancy_tags=';'.join(tags),known_original_toponyms=json.dumps([{'canonical':x[2],'surface':x[3]} for x in known],ensure_ascii=False),
            latin_dictionary_mentions_original=json.dumps(orig_names,ensure_ascii=False),latin_dictionary_mentions_parser=json.dumps(target_names,ensure_ascii=False),
            unmatched_original_toponyms=';'.join(missing),possible_mention_count_loss=';'.join(lost_count),relation_flags=';'.join(relation),
            existing_address=row['address'],existing_locations=row['locations'],existing_lat=row['lat'],existing_lon=row['lon'],existing_confidence=row['confidence']))
    with (ROOT/'results/translation_discrepancies.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    source_by_url={r['permalink']:r for r in rows}
    route_extra=[(i,r) for i,r in enumerate(routes,2) if r['permalink'] not in source_by_url]
    common_fields=['text','translated_text','address','lat','lon','bbox_ne_lat','bbox_ne_lon','bbox_sw_lat','bbox_sw_lon','locations']
    summary=dict(records=len(rows),translated_nonempty=sum(bool(r['translated_text']) for r in rows),languages=dict(Counter(r['detected_lang'] for r in rows)),
        class_counts=dict(Counter(r['audit_class'] for r in results)),possible_spatial_meaning_change=sum(r['possible_spatial_meaning_change'] for r in results),
        possible_toponym_change=sum(r['possible_toponym_change'] for r in results),possible_spatial_relation_change=sum(r['possible_spatial_relation_change'] for r in results),
        severe_inspected=sum(r['severe_inspected'] for r in results),requires_manual_inspection=sum(r['requires_manual_inspection'] for r in results),
        manually_inspected_annotations=len(MANUAL),known_toponym_coverage_hindi=sum(bool(mentions(r['text'])) for r in rows if r['detected_lang']=='hi'),
        relation_flags=dict(Counter(t for r in results for t in r['relation_flags'].split(';') if t)),
        available_urls=sum(bool(r['permalink']) for r in rows),unique_urls=len(set(r['permalink'] for r in rows if r['permalink'])),
        id_nonempty=sum(bool(r['id']) for r in rows),id_unique_nonempty=len(set(r['id'] for r in rows if r['id'])),
        precise_id_fields=sum(bool(re.fullmatch(r'\d{15,20}',r['id'])) for r in rows),
        source_route_values=sum(bool(r['route_coordinates']) for r in rows),route_file_records=len(routes),route_file_extra_fragment_rows=[i for i,r in route_extra],
        route_matches=len(routes)-len(route_extra),route_common_field_differences=dict(Counter(f for r in routes if r['permalink'] in source_by_url for f in common_fields if r[f]!=source_by_url[r['permalink']][f])),
        route_nonempty_matched=sum(bool(r['route_coordinates']) for r in routes if r['permalink'] in source_by_url),
        original_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'Data').rglob('*'))+[ROOT/'The_Geocoder.ipynb',ROOT/'Revised Identifiable Manuscript July 2026.docx',ROOT/'Reviews_March2026.docx',ROOT/'routes_batch1_highlighted.xlsx'] if p.is_file()})
    (OUT/'corpus_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='original_hashes'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
