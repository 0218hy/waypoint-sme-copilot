"""Guard intent check (SPEC §4.4) and side-question topic matching (SPEC §4.5).

A keyword baseline in English and Chinese decides; an optional model classifier can only add a
flag, never remove one. Code makes the decision; the model only words it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_F = re.IGNORECASE


def _any(*words: str) -> str:
    return "(?:" + "|".join(words) + ")"


LOAN = _any(
    r"webank",
    r"we\s*bank",
    r"wyd",
    r"微业贷",
    r"微众",
    r"(?:my|our|the)\s+(?:credit\s+)?line",
    r"(?:my|our)\s+(?:bank\s+)?loan",
    r"(?:the|this|that)\s+(?:bank\s+)?loan",
    r"loan\s+(?:money|funds|cash|proceeds)",
    r"borrowed\s+(?:money|funds|cash)",
    r"(?:bank|credit)\s+line",
    r"line\s+of\s+credit",
    r"我的贷款",
    r"贷款(?!行|方)",
    r"贷的钱",
    r"借来的钱",
    r"额度",
    r"授信",
)
# The home loan by name (a Singapore bank loan alone is R8's question, not R1's).
WEBANK = re.compile(
    r"webank|we\s*bank|wyd|微业贷|微众|my\s+(?:credit\s+)?line|我的贷款|额度"
    r"|(?:bank|credit)\s+line|line\s+of\s+credit|loan\s+(?:money|funds|cash|proceeds)|borrowed\s+(?:money|funds)"
    r"|贷款的钱|贷的钱|借来的钱",
    re.IGNORECASE,
)
SINGAPORE = _any(
    r"singapore",
    r"\bsg\b",
    r"overseas",
    r"abroad",
    r"新加坡",
    r"境外",
    r"海外",
    r"出海",
    r"\bpot\b",
    r"deposit",
    r"fit-?out",
    r"renovation",
    r"押金",
    r"装修",
    r"\bpte\b",
    r"shop there",
    r"new shop",
    r"新店",
    r"储蓄",
    r"\b(?:dbs|ocbc|uob|maybank)\b",
    r"星展",
    r"华侨银行",
    r"大华银行",
)
SG = r"(?:singapore|\bsg\b|overseas|abroad|新加坡|境外|海外|出去|过去|\b(?:dbs|ocbc|uob|maybank)\b|星展)"
# Singapore banks (a loan, credit or overdraft from one is borrowing in Singapore). Latin names are bounded by
# letters only, so "DBS贷款" matches too.
SG_BANK = (
    r"(?:(?<![a-z])(?:dbs|posb|ocbc|uob|maybank|stan(?:dard\s+)?chart(?:ered)?|hsbc|citi(?:bank)?|cimb|rhb)(?![a-z])"
    r"|星展|华侨银行|华侨|大华银行|大华|马来亚银行|渣打|汇丰|花旗"
    r"|(?:singapore|(?<![a-z])sg(?![a-z])|local|新加坡|狮城|当地|本地|那边)(?:'s)?\s*(?:的)?\s*(?:banks?|银行|金融机构))"
)
# Lenders whose only business is lending: naming one is asking to borrow.
SG_LENDER = (
    r"(?:(?:singapore|(?<![a-z])sg(?![a-z])|local|新加坡|狮城|当地|本地|那边)(?:'s)?\s*(?:的)?\s*(?:lenders?|financiers?|finance\s+compan(?:y|ies)|moneylenders?|贷款公司|财务公司|放贷)"
    r"|moneylenders?|licensed\s+lenders?|finance\s+compan(?:y|ies)|fintech\s+lenders?|online\s+(?:sme\s+|business\s+)?lenders?|lending\s+(?:app|platform)s?"
    r"|hire\s+purchase|equipment\s+(?:financ\w*|loans?|leas\w*)|fit-?out\s+(?:financ\w*|loans?)|vendor\s+financ\w*"
    r"|放贷人|持牌放贷|贷款公司|财务公司|融资租赁|设备贷|设备融资|装修贷|网贷平台)"
)
BORROW = (
    r"(?:borrow|loan|lend|financ|credit\s+(?:line|facility)|overdraft|grant|subsid|hire\s+purchase|instal?ments?|leasing"
    r"|贷|借|融资|透支|补助|补贴|资助|分期|授信|信贷)"
)
EFS = (
    r"(?<![a-z])efs(?![a-z])|enterprise\s+financing|enterprise\s*sg(?![a-z])|enterprise\s+singapore|esg\s+(?:loans?|grants?)"
    r"|企业融资计划|企业发展局|企发局|(?<![a-z])(?:psg|edg)(?![a-z])|(?:government|govt|state)[-\s]+(?:backed\s+)?(?:loans?|grants?)"
    r"|政府(?:贷款|补助|补贴|资助|基金|担保贷)|working\s+capital\s+loan|bridging\s+loan|\bsme\s+(?:loans?|financing)"
)
MONEY = r"(?:money|funds|cash|capital|savings|\bit\b|钱|资金|款|积蓄|存款)"
SEND = r"(?:send|transfer|wire|remit|move|pay|汇|转|打)"
HK = r"(?:hong\s*kong|\bhk\b|香港|澳门|macau)"
HOME_BILLS = r"(?:wages|payroll|salar(?:y|ies)|suppliers?|bills|rent at home|工资|薪水|货款|供应商|开支|房租)"
PROFIT = r"(?:profits?|earnings|cash|savings|利润|盈利|现金|赚的钱|自己的钱|自有资金)"
REPAY = re.compile(r"(?:repay\w*|pay(?:ing)?\s+(?:back|off|down))\s+(?:the\s+|my\s+|our\s+)?(?:webank\s+)?loan|loan\s+repayments?|还款|还贷", _F)  # noqa: E501
HOME_LOAN = re.compile(r"(?:my|our|the|this|that)\s+(?:bank\s+)?loan\b|我的贷款|我们的贷款|公司的贷款|这笔贷款", _F)  # noqa: E501
R8_AFTER = re.compile(
    r"after\s+(?:we\s+|the\s+shop\s+|it\s+)?(?:open(?:s|ed|ing)?|(?:have|'ve)\s+opened|start(?:ed)?\s+trading)\b|after\s+(?:the\s+)?opening"  # noqa: E501
    r"|once\s+(?:we'?re|we\s+are|the\s+shop\s+is|it'?s|it\s+is)\s+(?:open|opened|trading|running)"
    r"|once\s+we\s+(?:open|start\s+trading|have\s+(?:a\s+|some\s+)?(?:trading|track)\s+(?:history|record))"
    r"|(?:when|once|after)\s+we\s+(?:have|'ve\s+got|'ve\s+built)\s+(?:a\s+|some\s+)?(?:trading|track)\s+(?:history|record)"
    r"|after\s+(?:a|one|six|\d+)\s+(?:years?|months?)\s+of\s+trading|post-?opening"
    r"|(?:been|be|being)\s+open(?:ed)?\s+(?:for\s+)?(?:\w+\s+){0,2}(?:months?|years?)|(?:\w+)\s+(?:months?|years?)\s+(?:of\s+)?(?:trading|track\s+record|sales\b|records?)|traded\s+for"  # noqa: E501
    r"|trading\s+(?:records?|history)|(?:after|once|when)\b.{0,30}(?:trading|track\s+record)"
    r"|开了(?:快|近|差不多|有)?.{0,3}(?:年|个月)|(?:年|个月)(?:的)?(?:营业|经营|销售)?(?:流水|记录)|(?:营业|经营)记录|有了?.{0,6}(?:流水|记录)|开业.{0,4}(?:年|个月)(?:以|之)?后|"
    r"(?:开业|开张|营业|开起来|开店)(?:以|之)?后|有了?(?:经营|营业)(?:记录|流水|历史)|经营(?:一段时间|满|一年|半年)(?:以|之)?后|等(?:店)?开(?:业|张)(?:了)?(?:以|之)?后|开业满",
    _F,
)

# R4, the legal order: lender consent, then the ODI filing, then the bank registration, and only then money to
# Singapore. Each step is named here with its place in that order; money (3) comes last.
CONSENT = (
    r"(?:(?:lender|bank|webank|we\s*bank)(?:'s)?\s+(?:consent|approval|permission|sign-?off|go-?ahead|ok(?![a-z]))"
    r"|consent(?:\s+letter|\s+form)?|(?:ask|tell|inform|notify|clear\s+it\s+with)\w*\s+(?:webank|we\s*bank|the\s+(?:lender|bank))"  # noqa: E501
    r"|贷款行(?:的)?(?:同意|批准|许可)?|(?:银行|微众|微业贷)(?:的)?(?:同意|批准|许可)|同意函|同意书|征得.{0,6}同意|(?:告诉|通知|知会|问)(?:一下)?(?:微众|银行|贷款行)|(?:跟|和|向)(?:微众|银行|贷款行)(?:说|讲|打招呼|报备|汇报))"  # noqa: E501
)
FILING = r"(?:(?<![a-z])odi(?![a-z])|filing|paperwork|(?<![a-z])n?drc(?![a-z])|mofcom|commerce\s+(?:bureau|department)|备案|发改委|商务局|商务部门)"  # noqa: E501
REGISTRATION = (
    r"(?:(?:bank|safe|fx|forex|foreign[-\s]exchange|odi)\s+registration|regist(?:er|ered|ering|ration)\s+(?:it\s+)?(?:with|at)\s+(?:the\s+)?bank"  # noqa: E501
    r"|(?<!company )(?<!acra )(?<!business )(?<!shop )(?<![a-z])registration(?!\s+(?:of|for)\s+(?:the\s+)?(?:singapore\s+)?(?:company|pte|shop|business))"  # noqa: E501
    r"|外汇登记|银行登记|(?<!公司)(?<!工商)(?<!注册)登记)"
)
MONEY_OUT = (
    r"(?:(?<![a-z])(?:send|transfer|wire|remit|move)\w*\b(?!\s+(?:a\s+)?(?:message|email|form|application|document))"
    r"|pay\w*\s+(?:the\s+|a\s+|our\s+)?(?:\w+\s+)?(?:deposit|landlord|contractor|rent)|fund\w*\s+the\s+(?:singapore|sg|new)"
    r"|get\s+(?:the\s+|our\s+|some\s+)?(?:money|funds|cash|capital)\s+(?:over|across|out|there|abroad)"
    r"|汇款|汇钱|汇出|汇过去|汇到|转账|转钱|转过去|打款|打钱|付押金|付定金|付租金|出资"
    r"|(?:汇|转|打)(?:一部分|一些|一点|部分|一半|个)(?:钱|款|过去)?)"
)
_STEPS = [re.compile(p, _F) for p in (CONSENT, FILING, REGISTRATION, MONEY_OUT)]
# what joins two steps: the first one named comes first ("A then B", "A before B", "A之后B", "A再B") ...
R4_THEN = re.compile(
    r"\b(?:then|before|ahead\s+of|prior\s+to|followed\s+by|first|and\s+after\s+that)\b|然后|再|之后|以后|后再|接着|先于|才|先(?:办|做|弄|搞|走)", _F  # noqa: E501
)
# ... or the second one named comes first ("A after B", "A once B", "A之前B" = B before A)
R4_AFTER = re.compile(r"\b(?:after|once|following|later\s+than|when)\b|之前|以前|前(?:先|就)?", _F)
# words just before the first step named: it comes first ("after A, B", "先A…B") or second ("before A, B")
R4_LEAD_FIRST = re.compile(r"\b(?:after|once|following)\s+(?:the\s+|we\s+(?:get|have|do)\s+(?:the\s+)?)?$|(?:先|直接|马上|立刻)(?:去|把|做|办)?(?:银行)?$", _F)  # noqa: E501
R4_LEAD_SECOND = re.compile(r"\b(?:before|ahead\s+of|without\s+waiting\s+for)\s+(?:the\s+|we\s+(?:get|have|do)\s+(?:the\s+)?)?$", _F)  # noqa: E501
# a step put off until later, or done alongside the others
R4_LATER = re.compile(
    r"^.{0,24}?(?:\b(?:later|afterwards|next\s+(?:week|month)|in\s+a\s+(?:few\s+)?(?:weeks?|months?)|(?:should|will|can)\s+come|comes?\s+(?:later|after)|after(?=\s*(?:[.,!?;]|$))|after\s+the\s+fact|at\s+the\s+end|last(?!\s+(?:week|month|year|time|night|friday|monday|tuesday|wednesday|thursday|saturday|sunday))|down\s+the\s+(?:road|line)|retroactively|eventually|can\s+wait|in\s+parallel|at\s+the\s+same\s+time|simultaneously|alongside)\b"  # noqa: E501
    r"|以后再(?:补|办|弄|搞|说)|之后再(?:补|办|弄|搞|说)|后补|再补|补办|补上|补一下|回头|最后(?:再)?(?:补|办|弄)|再说|下个月|下周|过几天|过段时间|还要等|晚点|晚些|慢慢|事后|过后|同时|一起办|一并|并行|等等再)",
    _F,
)
R4_NOW = re.compile(r"\b(?:now|first|right\s+away|immediately|straight\s+away|today|asap|start|go\s+ahead)\b|先|现在|马上|立刻|直接|今天", _F)  # noqa: E501
R4_PARALLEL = re.compile(r"\b(?:in\s+parallel|at\s+the\s+same\s+time|simultaneously|all\s+at\s+once)\b|同时(?:办|做|进行|提交|走)|一起(?:办|做|提交|走)|并行", _F)  # noqa: E501
R4_PREPARE = re.compile(r"prepar|draft|gather|collect|paperwork\s+ready|准备|材料|整理", _F)
# a step that's skipped, kept from the lender, or treated as a formality
R4_SKIP = [
    re.compile(
        rf"(?:skip|avoid|bypass|go\s+around|get\s+around|work\s+around|forget(?:\s+about)?|ignore|leave\s+out|drop|no\s+need\s+(?:for|to)|don'?t\s+(?:need|bother|have)\s+(?:with\s+|to\s+)?(?:get\s+|do\s+|wait\s+for\s+|ask\s+(?:for\s+)?)?|not\s+bother|needn'?t|without\s+(?:telling|asking|informing|notifying|getting|waiting\s+for|doing|filing|any|the|a)?)\s*.{{0,20}}?(?:{CONSENT}|{FILING}|{REGISTRATION}|lender|paperwork|(?:webank|we\s*bank)(?!(?:'s)?\s*(?:loan|line|credit|money)))",  # noqa: E501
        _F,
    ),
    re.compile(
        rf"(?:{CONSENT}|{FILING}|{REGISTRATION}|webank|we\s*bank|the\s+lender|(?:the\s+)?bank(?!\s+registration)).{{0,30}}(?:(?:is|are|'s)\s+(?:just\s+|only\s+)?(?:a\s+)?(?:formality|optional|unnecessary|pointless|a\s+waste)|not\s+(?:really\s+)?(?:necessary|needed|required|important)|doesn'?t\s+(?:matter|need\s+to\s+(?:know|approve|agree))|don'?t\s+need\s+to\s+know|needn'?t\s+(?:know|be\s+told)|won'?t\s+(?:know|find\s+out|notice|check|care)|will\s+never\s+(?:know|find\s+out))",  # noqa: E501
        _F,
    ),
    re.compile(r"(?:keep|leave)\s+(?:webank|we\s*bank|the\s+(?:lender|bank))\s+(?:in\s+the\s+dark|out\s+of\s+(?:it|this|the\s+loop))|behind\s+(?:webank|we\s*bank|the\s+(?:lender|bank))(?:'s)?\s+back", _F),  # noqa: E501
    re.compile(
        r"(?:不用|不必|不需要|没必要|用不着|免了|省掉|省了|省去|跳过|绕过|绕开|不管|别管|不走|不经过|不办|不做|不去办|瞒着|不告诉|不通知|不让)(?:那个|这个|什么)?.{0,8}?(?:贷款行|微众|微业贷|银行|备案|登记|同意|手续|程序|流程|odi)",  # noqa: E501
        _F,
    ),
    re.compile(r"(?:备案|登记|同意函|手续|odi|微众|贷款行).{0,10}(?:就算了|不办了|不用办|省了|免了|可以不|没必要|无所谓|可有可无|走个?形式|不重要|不会知道|不知道的|发现不了|查不到|管不着|不用问|不用说|不用管|不会管|不在乎|不用通知|不用告诉|不用同意|不需要同意)", _F),  # noqa: E501
    # a step that can wait while the unit, the shop or the money can't
    re.compile(
        rf"(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,25}}(?:can\s+wait|can\s+come\s+later|isn'?t\s+urgent|is\s+not\s+urgent|不急|可以等|晚点再|先放一放|放一放)"  # noqa: E501
        r"(?=.{0,80}(?:unit|lease|shop|deposit|money|open|landlord|transfer|店|铺|租约|钱|开业|汇|押金))",
        _F,
    ),
    # the lender told last, once the rest is done
    re.compile(
        rf"(?:{CONSENT}|(?:tell|inform|ask)\w*\s+(?:webank|we\s*bank|the\s+lender)).{{0,15}}(?:after|once|when)\s+(?:it'?s|it\s+is|everything(?:'s|\s+is)?|the\s+rest|we'?ve|we\s+have|we'?re|all)\b.{{0,25}}(?:done|finished|over|sent|open|through|in\s+place|set\s+up)"  # noqa: E501
        r"|(?:回头|事后|最后|完了|办完|开业后|弄完)(?:再)?.{0,4}(?:跟|和|向|告诉|通知|知会)(?:一下)?(?:微众|银行|贷款行)",
        _F,
    ),
]
# every step but one done, and the money asked to go anyway
R4_EXCEPT = re.compile(
    rf"(?:except|but\s+not|apart\s+from|other\s+than|besides|minus|all\s+but)\s+(?:for\s+)?(?:the\s+)?(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,60}}(?:{MONEY_OUT})"  # noqa: E501
    rf"|(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,6}}(?:还没|没有|没|未)(?:办|做|弄|下来|批|拿到|完成|好)?.{{0,20}}(?:先|就|直接|马上)?.{{0,6}}(?:汇|转|打款|打钱|付|出资)",  # noqa: E501
    _F,
)
# each step reported done in turn ("consent: done. filing: done. registration: done.")
STEP_DONE = (
    r"(?:(?:is|are|'s|'re|has\s+been|have\s+been|have|has|were|was)\s+)?(?:now\s+|already\s+|all\s+|both\s+|also\s+)*"
    r"(?:done|complete[d]?|finished|approved|granted|issued|obtained|received|cleared|sorted|in\s+place|in\s+hand|through"
    r"|(?:come|gone)\s+through|wrapped\s+up|all\s+set|ticked\s+off|signed\s+off)\b"
    r"|(?:都|全部|全都|均|也)?(?:已经?|已)?(?:办完|办好|完成|走完|齐了|弄完|弄好|搞定|下来了?|批了|批下来|拿到|到手|通过|有了)"
)
# a step said to be still open: pending, later, missing or not yet done
STEP_OPEN = re.compile(
    r"\b(?:not|n't|pending|in\s+progress|submitted|lodged|applied|waiting|awaiting|still|yet|next\s+(?:week|month)|later"
    r"|tomorrow|soon|except|apart\s+from|other\s+than|underway|under\s+review|being\s+(?:processed|reviewed))\b"
    r"|还没|没有|没|未|在办|在审|审批中|审核中|提交|递交|受理|等|下周|明天|以后|之后再|回头|除了",
    _F,
)


def _all_steps_done(text: str) -> bool:
    """The three legal steps each named (with whatever qualifier the owner uses: WeBank's consent, the ODI
    filing, the SAFE registration) and said to be done, with none said to be still open."""
    named = [(s, e, p) for s, e, p in _steps_named(text) if p < 3]
    if {p for _, _, p in named} != {0, 1, 2}:
        return False
    first = named[0][0]
    done = list(re.finditer(STEP_DONE, text[first:], _F))
    if not done:
        return False
    # the last step named before a done word, and nothing open between the first step and that word
    last_step = max(e for _, e, _ in named)
    after = [m for m in done if first + m.start() >= last_step]
    if not after or first + after[0].start() - last_step > 60:
        return False
    return not STEP_OPEN.search(text[first : first + after[0].end()])


# all three steps done (and none named as missing): the money may go
R4_ALL_DONE = re.compile(
    r"(?:all\s+(?:three|3)|all\s+the\s+(?:steps|approvals)|every\s+step|everything|each\s+step|consent,?\s+(?:the\s+)?filing,?\s+and\s+(?:the\s+)?(?:bank\s+)?registration)"  # noqa: E501
    r".{0,40}(?:done|complete[d]?|finished|approved|registered|in\s+place|through|sorted)"
    r"|(?:三步|三个步骤|所有步骤|同意.{0,3}备案.{0,3}登记|手续)(?:都|全部|全都)?(?:已经)?(?:办完|办好|完成|走完|齐了|弄完|搞定)",
    _F,
)
# money while a step is only submitted or pending (a filing sent in is not a filing completed)
R4_PENDING = re.compile(
    rf"(?:{MONEY_OUT}).{{0,60}}(?:while|during|as\s+soon\s+as|once|when|in\s+the\s+meantime|meanwhile|because)\b.{{0,40}}(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,30}}(?:pending|in\s+progress|processing|being\s+(?:processed|reviewed)|under\s+review|submitted|lodged|sent\s+in|filed|applied|in\s+the\s+works|going|started|underway)"  # noqa: E501
    rf"|(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,30}}(?:is|are|'s|has\s+been|have\s+been)\s+(?:already\s+|all\s+|both\s+|still\s+)*(?:pending|in\s+progress|submitted|lodged|sent\s+in|underway|being\s+processed|under\s+review|in\s+the\s+works).{{0,60}}(?:{MONEY_OUT})"  # noqa: E501
    rf"|(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,15}}(?:isn'?t|is\s+not|aren'?t|are\s+not|hasn'?t|haven'?t|not)\s+(?:\w+\s+){{0,2}}?(?:yet|done|through|in|finished|complete[d]?|approved)\b.{{0,60}}(?:{MONEY_OUT})"  # noqa: E501
    rf"|(?:{CONSENT}|{FILING}|{REGISTRATION}).{{0,10}}(?:已经)?(?:提交|递交|在办|在审|审批中|审核中|受理|还没(?:批|下来|办好|完成|办完|拿到|办|做)|没(?:批|下来|办好|拿到)|还在走|在走流程|办着).{{0,30}}(?:汇|转|打款|打钱|付|出资)",  # noqa: E501
    _F,
)
# splitting or relaying transfers around the filing
R4_SPLIT = [
    re.compile(
        r"(?:in|into)\s+(?:several\s+|many\s+|lots\s+of\s+|a\s+few\s+)?(?:small(?:er)?\s+)?(?:chunks|batches|pieces|tranches|bits|lots|instal?ments|parts)"  # noqa: E501
        r"|(?:small(?:er)?|little)\s+(?:amounts|transfers|sums|batches|chunks|bits)|a\s+(?:little|bit)\s+at\s+a\s+time|bit\s+by\s+bit|piece\s*meal"  # noqa: E501
        r"|(?:under|below|beneath|within)\s+(?:the\s+)?(?:\$|us\$|usd\s*)?(?:50\s*k|50,?000|fifty\s+thousand|reporting\s+(?:threshold|limit)|threshold|annual\s+(?:quota|limit|allowance))"  # noqa: E501
        r"|(?:chop|break|split|carve|cut)\s+(?:it|the\s+\w+|them|that)?\s*(?:up|into)",
        _F,
    ),
    re.compile(
        r"(?:personal|individual|my|wife'?s?|husband'?s?|staff'?s?|employees'?|relatives'?|family'?s?|friends'?|everyone'?s|each\s+person'?s)\s+(?:annual\s+|yearly\s+|own\s+)?(?:fx|forex|foreign[-\s]exchange|currency|\$?50k|usd\s*50k)?\s*(?:quotas?|allowances?|limits?)"  # noqa: E501
        r"|(?:each|every\s+one|everyone)\s+(?:of\s+them\s+)?(?:buys?|exchanges?|converts?|sends?|remits?|wires?|transfers?)"
        r"|(?:use|borrow|pool|combine|tap|ask\s+for|get)\w*\b.{0,40}(?:fx|forex|foreign[-\s]exchange|currency|purchase)\s+(?:quotas?|allowances?)"  # noqa: E501
        r"|\w+(?:'s|s')\s+(?:fx|forex|foreign[-\s]exchange|currency)\s+(?:quotas?|allowances?)",
        _F,
    ),
    re.compile(
        r"小额|化整为零|分(?:几|多|好几|若干)?(?:笔|次|批)|分开(?:汇|转|打|换)|拆(?:成|开|分)|每(?:次|笔)(?:都)?(?:不超过|少于|控制在|别超过)|(?:个人|私人|家人|亲戚|员工|老婆|老公|太太|父母)(?:的)?(?:购汇|换汇|外汇)?(?:额度|便利化)|五万美元|5万美元|5万刀|(?:员工|家人|亲戚|朋友|同事|老婆|老公|父母|别人|他们|几个人).{0,8}(?:额度|名额).{0,6}(?:换汇|购汇|汇)",  # noqa: E501
        _F,
    ),
    # relays: another company, a person, an invoice or an informal channel
    re.compile(
        r"(?:through|via|by\s+way\s+of|route\w*\s+(?:it\s+|them\s+)?(?:through|via)|use)\s+(?:a\s+|an\s+|my\s+|our\s+|the\s+|his\s+|her\s+)?(?:friend|cousin|relative|brother|sister|uncle|partner|agent|middleman|broker|third[-\s]party|another\s+company|other\s+company|offshore|bvi|cayman|dubai|malaysia|labuan|crypto|usdt|stablecoin|bitcoin|money\s+changer|remittance\s+(?:shop|agent))"  # noqa: E501
        r"|(?:usdt|crypto(?:currency)?|stablecoin|bitcoin|比特币|虚拟币|泰达币|稳定币|u币)"
        r"|(?:fake|inflat\w*|padd(?:ed|ing)|over-?invoic\w*|overpay\w*|dummy|sham)\s+.{0,15}(?:invoice|contract|trade|purchase|order|supplier|payment)"  # noqa: E501
        r"|(?<![a-z])(?:as|call\s+it|label\s+it|disguis\w*\s+(?:it\s+)?as|pass\s+(?:it\s+)?off\s+as|dress\s+(?:it\s+)?up\s+as|book\s+it\s+as|treat\s+it\s+as|under\s+the\s+name\s+of)\s+(?:a\s+|an\s+)?(?:trade|supplier|purchase|import|service|consult\w*|management|royalt\w*|licen[cs]e|franchise|marketing|brand(?:ing)?|tech(?:nology)?|advisory)\b\s*(?:fees?|payments?|invoices?|costs?|charges?)?",  # noqa: E501
        _F,
    ),
    re.compile(
        r"(?:以|按|当|当作|算作|算成|做成|伪装成|包装成|假装|名义).{0,8}(?:货款|服务费|咨询费|管理费|贸易|采购|进口|加盟费|特许|品牌费|技术费|设备款)"
        r"|(?:货款|服务费|咨询费|管理费|贸易款|采购款|加盟费|品牌费|技术费).{0,8}(?:名义|的形式|的方式)"
        r"|(?:虚开|虚构|多开|做高|抬高|假的?).{0,6}(?:发票|合同|货款|贸易|订单)"
        r"|(?:朋友|亲戚|熟人|中介|换汇的人|别人|第三方|他|她).{0,12}(?:在新加坡|那边|新加坡的).{0,10}(?:先)?(?:付|垫|出|给).{0,20}(?:国内|这边|人民币).{0,8}(?:给|还|转)",  # noqa: E501
        _F,
    ),
    re.compile(
        r"(?:pay|invoice|bill|charge)\w*\s+(?:the\s+|our\s+)?(?:singapore|sg|new)\s+(?:company|entity|pte|side|shop)\s+(?:a\s+|an\s+)?(?:\w+\s+)?(?:fees?|invoices?|royalt\w*|commission)"  # noqa: E501
        r"|(?:singapore|sg)\s+(?:company|entity|pte|side)\s+(?:can\s+|will\s+)?(?:invoice|bill|charge)\w*\s+(?:us|our|the\s+shenzhen|the\s+home)"  # noqa: E501
        r"|(?:给|向|付给)新加坡(?:公司|主体|那边).{0,4}(?:付|支付|交|打)?.{0,4}(?:服务费|咨询费|管理费|品牌费|加盟费|技术费|特许费)",
        _F,
    ),
    re.compile(
        r"(?:settle\s+up|square\s+up|pay\s+\w+\s+back|repay\s+\w+|reimburse\s+\w+|make\s+it\s+up\s+to\s+\w+)\s+.{0,10}(?:in\s+(?:china|shenzhen|rmb|yuan|cny)|here\b|at\s+home|back\s+home)",  # noqa: E501
        _F,
    ),
    re.compile(
        r"(?:pay|front|cover|lend|advance)\w*\s+.{0,40}(?:(?:we|i)(?:'ll|\s+will|\s+can)?\s+(?:pay|repay|give|transfer|hand)\w*\s+.{0,20}(?:back\s+)?(?:in\s+(?:china|shenzhen|rmb|yuan|cny)|here|at\s+home))",  # noqa: E501
        _F,
    ),
]
# the pre-investment allowance (前期费用): at most 15% of the plan, for costs before the company exists,
# never the deposit
PREINV = r"(?:pre-?investment|preliminary\s+(?:expenses?|costs?|funds?|allowance)|pre-?odi\s+(?:funds?|money|allowance)|前期费用|前期费|前期资金|前期款)"  # noqa: E501
R4_ALLOWANCE = [
    re.compile(
        rf"{PREINV}.{{0,60}}(?:deposit|定金|订金|押金|保证金|fit-?out|renovat\w*|装修|rent\b|租金|房租|lease|租约|equipment|设备)"
        rf"|(?:deposit|定金|订金|押金|保证金|fit-?out|renovat\w*|装修|租金|房租).{{0,40}}{PREINV}",
        _F,
    ),
    re.compile(
        rf"{PREINV}.{{0,50}}(?:\bmost\b|majority|bulk|\bhalf\b|\ball\b|whole|entire|everything|more\s+than|\bover\b|above|beyond|stretch|raise|increase|bump|top\s+up|max(?:imum)?\s+(?:it\s+)?out|as\s+much\s+as|bigger|larger|大部分|一半|全部|所有|都用|超过|多于|提高|调高|多报|多申请|做大|尽量多|放大|撑大|多算|多汇|多弄|多拿)"  # noqa: E501
        rf"|(?:\bmost\b|majority|bulk|\bhalf\b|\ball\b|whole|entire|stretch|raise|increase|bump\s+up|大部分|一半|全部|提高|多报|多申请|做大|尽量多|多汇|多弄).{{0,40}}{PREINV}",  # noqa: E501
        _F,
    ),
]
R4_ALLOWANCE.append(re.compile(rf"{PREINV}.{{0,40}}(?:[二两三四五六七八九]成|(?:百分之)?(?:二|三|四|五|六|七|八|九)十)", _F))  # noqa: E501
R4_PCT = re.compile(rf"{PREINV}.{{0,60}}?(\d{{1,3}})\s*(?:%|percent|per\s+cent|成)|(\d{{1,3}})\s*(?:%|percent|per\s+cent)\s*.{{0,40}}{PREINV}", _F)  # noqa: E501


def _steps_named(text: str) -> list[tuple[int, int, int]]:
    """(start, end, place in the legal order) for each step or money named, longest match first."""
    found: list[tuple[int, int, int]] = []
    for place, pat in enumerate(_STEPS):
        for m in pat.finditer(text):
            if not any(s <= m.start() < e or s < m.end() <= e for s, e, _ in found):
                found.append((m.start(), m.end(), place))
    return sorted(found)


R4_ROUTE = re.compile(
    rf"{HK}|underground|地下钱庄|对敲|personally|myself|in\s+my\s+(?:own\s+)?name|personal\s+account|个人名义|私人账户|以个人|自己的账户",  # noqa: E501
    _F,
)


def r4_all_done(text: str) -> bool:
    """Every legal step done, with none named as still to do, and the money not split, relayed or sent
    personally (those stay R4 whatever is done)."""
    missing = re.search(r"\bexcept\b|还没|没有办|未办|没办", text, _F)
    if not (R4_ALL_DONE.search(text) or _all_steps_done(text)) or R4_EXCEPT.search(text) or missing:
        return False
    routed = R4_ROUTE.search(text) or any(p.search(text) for p in (*R4_SPLIT, *R4_ALLOWANCE))
    return not routed


def r4_order(text: str) -> str | None:
    """The legal steps named out of order, put off, done side by side or skipped, or money before all three
    are done; splitting or relaying transfers; the pre-investment allowance stretched. The matched words, or
    None."""
    if r4_all_done(text):
        return None
    for pat in (*R4_SKIP, R4_PENDING, R4_EXCEPT, *R4_SPLIT, *R4_ALLOWANCE):
        m = pat.search(text)
        if m:
            return m.group(0)
    for m in R4_PCT.finditer(text):
        pct = int(m.group(1) or m.group(2))
        if 15 < pct <= 100:
            return m.group(0)
    named = _steps_named(text)
    places = {p for _, _, p in named}
    for i, (s1, e1, p1) in enumerate(named):
        # put off while a later step (or the money) goes ahead
        later = R4_LATER.search(text[e1:])
        if later and any(
            p > p1 and (s < s1 or R4_NOW.search(text[max(0, s - 8) : e + 12])) for s, e, p in named
        ):
            return text[s1 : e1 + later.end()]
        lead = text[max(0, s1 - 30) : s1]
        for s2, e2, p2 in named[i + 1 :]:
            if p2 == p1 or s2 - e1 > 60:
                continue
            gap = text[e1:s2]
            if R4_LEAD_FIRST.search(lead):
                first, second = p1, p2
            elif R4_LEAD_SECOND.search(lead):
                first, second = p2, p1
            elif R4_THEN.search(gap):
                first, second = p1, p2
            elif R4_AFTER.search(gap):
                first, second = p2, p1
            else:
                continue
            if first > second:
                return text[s1:e2]
    side_by_side = R4_PARALLEL.search(text)
    if len(places) >= 2 and side_by_side and not R4_PREPARE.search(text):
        return side_by_side.group(0)
    # a later step, or the money, first
    m = re.search(
        rf"(?:{MONEY_OUT}|{REGISTRATION})\s*(?:\S+\s+){{0,3}}?first\b|(?:先|直接|马上|立刻)(?:去|把)?(?:银行)?(?:登记|汇|转账|打款|打钱|付押金|出资)",
        text,
        _F,
    )
    if m and (len(places) >= 2 or "登记" in m.group(0) or "regist" in m.group(0).lower()):
        return m.group(0)
    return None


# R6, cash before commitment: nothing commits the owner to the unit (the lease signed, the letter of offer
# or LOI accepted, a deposit paid to hold it) until the deposit, the whole fit-out and the rent before opening
# are in Singapore. The plan is made before the money moves, so a request to commit counts as before the money
# unless it says all of it is already there.
COMMIT = (
    r"(?:(?:put|get)\s+(?:our|my|a|the|your)\s+signatures?\s+on|(?<![a-z])(?:sign(?:ing|ed)?|ink|execute|accept(?:ing)?|take\s+up|lock\s+(?:in|down|up)|secure|commit(?:ting)?\s+to|close\s+(?:on|out)|seal|agree\s+to|say\s+yes\s+to|countersign|go\s+ahead\s+with|put\s+(?:pen|our\s+name)\s+to)(?![a-z])"  # noqa: E501
    r"|(?:put|lay)\s+(?:down\s+)?(?:a|the|our)\s+(?:\w+\s+)?(?:deposit|down\s*payment)|pay\w*\s+(?:a|the|our)\s+(?:holding|booking|security|good[-\s]faith|earnest|reservation|option)\s+(?:deposit|fee|money)"  # noqa: E501
    r"|(?:reserve|book|hold|grab|snap\s+up)\s+(?:the|this|that|it)\s*(?:unit|space|shop|site|place|lot)?\s+(?:with|by\s+paying|for)\s+(?:a\s+|the\s+)?(?:\w+\s+)?(?:deposit|fee)"  # noqa: E501
    r"|签(?!证|名)|盖章|定下|订下|锁定|锁住|拿下|占住|接受|答应|交(?:个|了)?(?:定金|订金|押金|诚意金|意向金|保证金)|付(?:个|了)?(?:定金|订金|诚意金|意向金|保证金))"  # noqa: E501
)
LEASE = (
    r"(?:lease|tenancy|rental\s+(?:agreement|contract)|letter\s+of\s+offer|offer\s+letter|(?<![a-z])lo[oi](?![a-z])|letter\s+of\s+intent"  # noqa: E501
    r"|(?:the|this|that|landlord'?s?)\s+offer|(?:the|this|that)\s+(?:unit|space|shop(?:\s*front)?|site|place|location|lot|premises)"
    r"|租约|租赁合同|租房合同|租赁协议|租赁意向|合同|要约|意向书|意向函|铺位|铺面|店面|门面|(?:这|那)(?:个|间|家)?(?:铺|店|位置))"
)
R6_COMMIT = re.compile(
    rf"{COMMIT}.{{0,30}}{LEASE}|{LEASE}.{{0,12}}{COMMIT}|签约|签租"
    r"|(?:reserve|book|hold|grab|snap\s+up|secure|lock\s+in)\s+(?:the|this|that|it)\s*(?:unit|space|shop|site|place|lot)?\s+(?:with|by\s+paying|for)\s+(?:a\s+|the\s+)?(?:\w+\s+)?(?:deposit|fee)",  # noqa: E501
    _F,
)
# signing with no object named ("then we sign"): counts only with an early or part-money word
R6_SIGN = re.compile(
    r"(?:(?:^|[.;,!?]\s*)|(?<![a-z])(?:we|i|then|and|to|will|'ll|can|just|let'?s)\s+)sign(?:ing)?\b(?!\s+(?:up|in\b|out|off|for\s+the\s+(?:account|loan)|(?:the\s+)?(?:consent|application|filing|forms?|papers|documents?)))"  # noqa: E501
    r"|就签|再签|先签|签了吧|签吧|签掉|赶紧签|快签|签下来",
    _F,
)
# paying the deposit to the landlord commits the owner (sending it to the Singapore company's account doesn't)
R6_DEPOSIT = re.compile(
    r"(?:pay|put\s+down|hand\s+over|place)\w*\s+(?:the\s+|a\s+|our\s+)?(?:\w+\s+)?deposit(?!\s+(?:in)?to\s+(?:the\s+|our\s+)?(?:singapore|sg|company|account|pte))"  # noqa: E501
    r"|(?:交|付)(?:个|了)?(?:押金|定金|订金|诚意金|意向金)|(?:押金|定金|订金|诚意金|意向金|保证金)(?:先|就|也)?(?:交|付)(?:了|掉|上)?",
    _F,
)
R6_EARLY = re.compile(
    r"\b(?:now|today|tonight|tomorrow|this\s+(?:week|weekend|month|friday|monday)|right\s+away|immediately|asap|straight\s+away|first|early|earlier|ahead|quick(?:ly)?|before|while|meanwhile|in\s+the\s+meantime|without\s+waiting|not\s+(?:yet|all|there|in)|yet|haven'?t|hasn'?t|isn'?t|aren'?t|later|afterwards|then\s+(?:send|transfer|move|wire|pay|raise|find|sort|top)|so\s+(?:we|i)\s+don'?t\s+lose|someone\s+else|won'?t\s+wait|only|just\s+the|part\s+of|half|the\s+rest|remaining|remainder|balance|still|catch\s+up|follow|on\s+the\s+way|in\s+transit|tight|deadline|expires?|before\s+it'?s\s+gone|gone|will\s+come|comes?\s+later|(?:will|can)\s+(?:come|follow|catch\s+up|arrive))\b"  # noqa: E501
    r"|先|现在|马上|立刻|立即|今天|明天|这周|本周|这个月|赶紧|赶快|尽快|提前|早点|还没|没到|未到|不等|之前|同时|再汇|后汇|再补|后补|再说|再转|再筹|慢慢|别人|抢|催|不等人|只有|只到|一部分|一半|剩下|其余|余款|后面|以后|之后|回头|边.{0,6}边|来不及|等不了|等不及",  # noqa: E501
    _F,
)
R6_ASK = re.compile(
    r"\b(?:let'?s|go\s+ahead|we'?ll|i'?ll|we\s+will|i\s+will|want\s+to|wanna|going\s+to|gonna|can\s+(?:we|i)|could\s+(?:we|i)|just|need\s+to|have\s+to|got\s+to|gotta|must|please)\b"  # noqa: E501
    r"|(?:^|[.;,!]\s*)(?:sign|accept|lock|secure|commit|pay|book|get|have)\b"
    r"|帮我|我要|我想|我们要|我们想|就|吧|准备|打算|直接|赶紧|得",
    _F,
)
# all of the money already in Singapore (and nothing left to follow)
R6_ALL_IN = re.compile(
    r"(?:all|every|whole|entire|full|both|everything)\b.{0,50}?\b(?:is|are|has|have|'s|'re)?\s*(?:already\s+|all\s+|both\s+)?(?:been\s+)?(?:in|arrived|landed|there|through|transferred|sent\s+over|cleared)\b"  # noqa: E501
    r"|(?:deposit|fit-?out|rent).{0,60}(?:all|both|everything|fully).{0,15}(?:in|there|arrived|landed|transferred)\b"
    r"|deposit.{0,40}fit-?out.{0,40}rent.{0,30}(?:(?:is|are)\s+(?:now\s+|already\s+)?in|arrived|landed|transferred|cleared)\b"
    r"|押金.{0,10}装修.{0,10}(?:房租|租金).{0,8}(?:都|全)?(?:已经)?(?:到|在|汇到|进)"
    r"|(?:钱|资金|款项?|押金.{0,12}装修.{0,12}租金).{0,6}(?:都|全部|全|已经全部|全都)(?:已经)?(?:到账|到位|汇到|到了|汇过去|过去了|在新加坡|到(?:了)?新加坡|进(?:了)?新加坡)"
    r"|(?:全部|所有)(?:的)?(?:钱|资金|款项?)(?:都)?(?:已经)?(?:到账|到位|到了|汇过去|汇到|在新加坡|到(?:了)?新加坡|进(?:了)?新加坡)",
    _F,
)
R6_PARTIAL = re.compile(
    r"(?:fit-?out|renovation|rent|rest|remaining|remainder|balance|money|cash|funds)\s+(?:\w+\s+){0,4}?(?:later|afterwards|after|can\s+follow|will\s+follow|to\s+follow)"  # noqa: E501
    r"|\bonly\s+(?:the|part|half)|just\s+the\s+deposit|part\s+of|\bhalf\b|剩下|其余|余款|(?:装修|租金|房租|钱|款).{0,6}(?:以后|之后|后面|回头)再?(?:汇|转|补|付|到|凑)|再汇|后汇|再补|一部分|一半|只有|只到",
    _F,
)

# signing tied to the money arriving ("we'll sign after the money arrives"), with nothing done before it
R6_AFTER_MONEY = (
    r"(?:after|once|when|as\s+soon\s+as|only\s+(?:when|after|once)|until|等|待)\s*.{0,20}?(?:money|funds|cash|transfers?|everything|it\s+all|钱|资金|款项?)"  # noqa: E501
    r".{0,20}?(?:arrives?|arrived|lands?|landed|is\s+in|are\s+in|is\s+there|clears?|cleared|comes?\s+through|到账|到位|到了|汇到)"
)
R6_TIED = re.compile(rf"{COMMIT}.{{0,40}}{R6_AFTER_MONEY}|{R6_AFTER_MONEY}.{{0,40}}{COMMIT}", _F)
R6_NOW = re.compile(r"\b(?:now|today|first|right\s+away|immediately|asap|this\s+week)\b|先|现在|马上|立刻|今天|这周", _F)  # noqa: E501
# a question about when or what happens (with no push in it) is learning about R6
R6_QUESTION = re.compile(
    r"^\s*(?:what\s+(?:happens|would\s+happen|could\s+go\s+wrong|if\s+(?:the|our)\s+money)|when\s+(?:can|should|do|will|could)|how\s+(?:soon|early|long)|why\s+(?:do|must|should)\s+(?:i|we)|is\s+it\s+(?:risky|dangerous|safe))\b"  # noqa: E501
    r"|什么时候(?:可以|能|才能|应该)?签|签.{0,12}(?:会怎样|会怎么样|有什么(?:风险|后果))|为什么.{0,10}(?:不能|要等).{0,10}签",
    _F,
)
R6_PUSH = re.compile(r"\b(?:just|anyway|still|let'?s|go\s+ahead|now)\b|就|吧|直接|先|现在", _F)


def r6_money_in(text: str) -> bool:
    """All of the money (deposit, whole fit-out, rent before opening) in Singapore, none to follow."""
    return bool(R6_ALL_IN.search(text)) and not R6_PARTIAL.search(text)


def r6_commit(text: str) -> str | None:
    """A request to commit to the unit before all the money is in Singapore. The matched words, or None."""
    m = R6_COMMIT.search(text) or R6_DEPOSIT.search(text)
    if not m and (m := R6_SIGN.search(text)) and not (R6_EARLY.search(text) or R6_PARTIAL.search(text)):
        return None
    if not m:
        return None
    if r6_money_in(text):
        return None  # the money is in: signing is the next lawful step
    if R6_TIED.search(text) and not R6_PARTIAL.search(text) and not R6_NOW.search(text):
        return None  # signing waits for the money
    if R6_QUESTION.search(text) and not R6_PUSH.search(text):
        return None
    if R6_EARLY.search(text) or (R6_COMMIT.search(text) and R6_ASK.search(text)):
        return m.group(0)
    return None


# R2, no borrowing to free up profit: while WeBank borrowing is above its usual level the Singapore set-aside
# and transfers pause (they restart once it's back to normal), and borrowing for home bills so that profit can
# go abroad is indirect diversion (置换).
HOME_LOAN_WORD = (
    rf"(?:{LOAN}|borrow\w*|facility|drawdown|draw\s*down|drawn|drew|(?:draw|pull|take)\w*\s+(?:\w+\s+)?(?:on|from|off)\s+(?:the\s+|our\s+)?(?:line|loan|facility|webank)"  # noqa: E501
    r"|top(?:ping)?\s+up\s+(?:the\s+|our\s+)?(?:loan|line|facility)"
    r"|draw\w*\s+(?:down\s+)?(?:another\s+|an?\s+extra\s+|some\s+|more\s+)?(?:\d[\d.,]*\s*(?:k|m|million|万|w)?|money|cash|funds)\b|(?:多|再)?(?:借|贷|提款|用款|提额|放款))"
)
# the Singapore saving or the transfers (what pauses)
SETASIDE = (
    r"(?:set-?asides?|(?<![a-z])pot(?![a-z])|(?:singapore|sg)\s+(?:\w+\s+)?(?:savings?|saving|money|transfers?|fund|account|side)"
    r"|monthly\s+(?:saving|savings|transfers?|amount)|transfers?|remittances?|saving\s+for\s+(?:singapore|the\s+(?:new\s+)?shop)"
    r"|留存|储蓄|存款|存钱|汇款|汇钱|每月(?:存|汇|留)|新加坡(?:的|那边)?(?:钱|存款|储蓄|账户|资金|汇款|留存))"
)
# borrowing above its usual level, now
LOAN_HIGH = re.compile(
    rf"{HOME_LOAN_WORD}.{{0,40}}(?:(?:more|higher|bigger|larger)\s+than\s+(?:\w+\s+)?(?:normal|usual|before|average|we\s+usually)|above\s+(?:\w+\s+)?(?:normal|usual|average)|over\s+(?:\w+\s+)?(?:usual|normal)|(?:is|'s|are|'re|went|gone)\s+up\b|spike|surge|jump|peak|extra\b|elevated|maxed|high(?:er)?\b|heav(?:y|ier)|a\s+lot\s+more|more\s+this)"  # noqa: E501
    rf"|(?:extra|more|additional|heavier|higher)\s+(?:\w+\s+)?(?:borrowing|drawdowns?|loans?|debt)|{HOME_LOAN_WORD}\s+(?:\w+\s+)?(?:extra|more)\b"
    r"|(?:借|贷|额度|余额|提款|用款|欠款|负债).{0,10}(?:比平时|比往常|比以前|比上个月|高于|偏高|超过平时|超出|多了|高了|增加|涨了|上去了|多一些|多一点|大了|有点高|比较高|太高|很高)"
    r"|多借|多贷|多提|多用了?(?:一些|一点)?(?:额度|贷款)",
    _F,
)
# the set-aside or the transfers kept going, or their pause lifted
KEEP_GOING = re.compile(
    r"\b(?:(?:don'?t|do\s+not|never|no\s+need\s+to|shouldn'?t|mustn'?t|won'?t)\s+(?:\w+\s+){0,2}?(?:stop|pause|freeze|halt|suspend|hold\s+(?:back|off)|interrupt|cut\s+off)"  # noqa: E501
    r"|keep\w*|carry\s+on|continu\w*|still\s+(?:want|need|go|send|put|do|make|have|transfer|save|run|wire|move)\w*|go(?:es)?\s+out\s+(?:this|next|every|as)|leave\s+(?:\w+\s+){0,4}?(?:running|going|on|as\s+(?:it\s+is|before))|as\s+(?:before|usual|normal|planned)|anyway|regardless"
    r"|override|overrid\w*|cancel\w*\s+(?:the\s+)?pause|lift\w*\s+(?:the\s+)?pause|skip\w*\s+(?:the\s+)?pause|unpause|ignore\s+(?:the\s+)?(?:pause|rule|check)"
    r"|(?:so|so\s+that)\s+(?:nothing|it|the\s+\w+|they)\s+(?:doesn'?t|don'?t|won'?t|never)\s+(?:stop|pause)|(?:so|so\s+that)\s+nothing\s+pauses|not\s+(?:be\s+)?paused)\b"  # noqa: E501
    r"|别停|不要停|不停|不能停|停不得|照常|照样|继续|不要暂停|别暂停|不用暂停|不暂停|先不要?暂停|取消.{0,4}暂停|暂停.{0,4}(?:取消|去掉|关掉)|还是要|一样(?:存|汇|留)|按原计划|不受影响|不管",
    _F,
)
# the borrowing back to its usual level, said as done (not "will be next month")
BACK_TO_USUAL = re.compile(
    r"(?<!will\s)(?<!'ll\s)(?:(?:is|'s|are|has\s+come|have\s+come|came|went|got|gone|now)\s+(?:all\s+)?(?:back\s+)?(?:down\s+)?(?:to|at)\s+(?:where\s+it\s+(?:normally|usually)\s+is|(?:its|our|the)?\s*(?:usual|normal)(?:\s+level)?)|(?:at|back\s+to)\s+(?:its|our|the)\s+(?:usual|normal)\s+level\s+again|(?:repaid|paid\s+(?:back|off|down))\s+(?:the|all\s+the|that)?\s*(?:extra|additional))"  # noqa: E501
    r"|(?:已经?|已)(?:降|回|恢复)(?:到|回)?(?:了)?(?:平时|正常|往常|原来)|(?:降回|回到|恢复到?)(?:了)?(?:平时|正常|往常|原来)的?(?:水平)?|(?:已经?)?还清了?|恢复正常了",
    _F,
)
FUTURE = re.compile(r"\b(?:will|'ll|going\s+to|next\s+(?:week|month)|soon|by\s+(?:the\s+)?(?:end|next))\b|会|下个月|下周|很快|马上就|过几天", _F)  # noqa: E501
# a home cost the loan is for
HOME_COST = (
    r"(?:wages|payroll|salar(?:y|ies)|bonus(?:es)?|suppliers?|stock|inventory|purchases|ingredients|rents?\b|bills?\b|utilities|electricity|water"
    r"|social\s+insurance|(?:income\s+|corporate\s+|vat\s+)?tax(?:es)?\b|vat\b|expenses|overheads|running\s+costs|operating\s+costs|costs?\s+at\s+home"
    r"|(?:home|shenzhen|domestic)\s+(?:shops?|costs?|side|business)"
    r"|工资|薪水|奖金|货款|供应商|进货|备货|原料|房租|租金|水电|社保|公积金|税|开销|开支|费用|成本|账单|周转|日常)"
)
# profit or the company's own cash, freed for Singapore
FREED = (
    r"(?:profits?|earnings|takings|revenue|cash|own\s+money|our\s+money|savings|surplus|free(?:s|d)?\b|free\s+up|freeing|leaves?|left\s+over|spare"
    r"|腾|省下|空出|利润|赚的钱|盈利|现金|自有资金|自己的钱|营业款|营收|收入)"
)
SG_DEST = rf"(?:{SG}|{SETASIDE}|new\s+shop|the\s+(?:new\s+)?outlet|出海|新店)"
R2_LINK = re.compile(
    r"\b(?:so|so\s+that|then|that\s+(?:way|leaves|frees)|leaves|leaving|frees|freeing|free\s+up|and\s+(?:put|send|move|use|keep|save)|instead|while|meanwhile|which\s+(?:means|lets))\b"  # noqa: E501
    r"|腾出|省下|空出|留给|留着|用来|拿去|就能|这样|然后|再把|把.{0,8}(?:省|留|腾)",
    _F,
)
# making the borrowing look usual
R2_USUAL = re.compile(
    r"(?:repay|pay\s+(?:back|off|down)|clear)\w*\s+(?:\w+\s+){0,6}?(?:before|ahead\s+of)\s+(?:the\s+|your\s+|its\s+)?(?:check|month-?end|cut-?off|snapshot|review|test|date).{0,60}(?:draw|borrow|take)\w*\s+(?:it\s+)?(?:again|back|out)"  # noqa: E501
    r"|(?:raise|lift|increase|bump\s+up|reset|change|move|redefine|adjust)\w*\s+(?:\w+\s+){0,5}?(?:usual|normal|baseline|threshold)\s*(?:borrowing\s+)?(?:level|line|limit|amount|figure)?"
    r"|(?:leave|keep|take)\s+(?:\w+\s+){0,4}?(?:drawdown|loan|borrowing|balance)\s+(?:\w+\s+){0,2}?out\s+of\s+(?:the\s+)?(?:count|calculation|check|figures?)|(?:don'?t|do\s+not|shouldn'?t)\s+count\s+(?:\w+\s+){0,4}?(?:drawdown|loan|borrowing)"  # noqa: E501
    r"|(?:move|shift|park|switch|refinanc)\w*\s+(?:\w+\s+){0,5}?(?:balance|loan|borrowing|debt)\s+(?:\w+\s+){0,4}?(?:to|with|at)\s+(?:another|a\s+different|other)\s+(?:bank|lender)"
    r"|(?:doesn'?t|won'?t|don'?t)\s+(?:show|look|count)\s+(?:as\s+)?(?:high|above|more)"
    r"|(?:repay|pay\s+(?:\w+\s+){0,2}?back|pay\s+(?:\w+\s+)?off|clear)\w*\b.{0,60}(?:(?:take|draw|borrow|pull)\w*\s+(?:it\s+|them\s+)?(?:out\s+|down\s+)?again|redraw\w*|re-draw\w*)"
    r"(?=.{0,80}(?:pot|set-?aside|singapore|sg\b|transfer|notice|check|count|show|saving))"
    r"|(?:检查|查|统计|月底|月末|截止).{0,8}(?:前|之前).{0,6}(?:还|还上|还掉|还清).{0,20}(?:再|又)(?:借|贷|提|用)"
    r"|(?:还上|还掉|还清).{0,15}(?:检查|统计|月底|月初|过了).{0,10}(?:再|又)(?:借|贷|提)"
    r"|还(?:上|掉|清|了)?.{0,15}(?:再|又|重新)(?:借|贷|提)(?:出来)?(?=.{0,30}(?:留存|储蓄|新加坡|汇|看不出|发现|检查|统计|暂停))"
    r"|(?:调高|提高|改高|上调|重新设定|改一下|调整).{0,8}(?:正常|平时|基准|常规)(?:的)?(?:借款|贷款)?(?:水平|额度|线)?"
    r"|(?:正常|平时|基准|常规)(?:的)?(?:借款|贷款)?(?:的)?(?:水平|线|标准|额度|基数)?.{0,6}(?:调高|提高|改高|上调|调整|放宽|改大)"
    r"|(?:这笔|那笔|这次|那次)(?:提款|借款|贷款|用款).{0,6}(?:别|不要|不用|不)(?:算|计|统计)"
    r"|(?:转|挪|移)到(?:别的|其他|另一家)(?:银行|贷款)",
    _F,
)
# the pause accepted ("I understand the Singapore saving pauses meanwhile")
PAUSE_OK = re.compile(
    r"\b(?:understand|accept|expect|fine\s+(?:with|that)|ok(?:ay)?\s+(?:with|that))\b[^.;!?]{0,40}\bpaus\w*|\bpaus\w*\s+(?:\w+\s+)?(?:is\s+fine|that'?s\s+fine|meanwhile|for\s+now|in\s+the\s+meantime)\b"  # noqa: E501
    r"|(?:先)?停着?(?:也)?没关系|暂停(?:也)?没关系|停(?:一下|一阵|几个月)?(?:也)?(?:可以|行|没事)|先停着|暂停就暂停",
    _F,
)


def r2_free_profit(text: str) -> str | None:
    """Borrowing at home to free up profit for Singapore, or keeping the set-aside going while the borrowing
    is above usual, or making the borrowing look usual. The matched words, or None."""
    redraw = re.search(rf"{HOME_LOAN_WORD}.{{0,40}}(?:again|back\s+out|再借|又借|再贷)", text, _F)
    if REPAY.search(text) and not redraw:
        m = R2_USUAL.search(text)
        return m.group(0) if m else None
    if m := R2_USUAL.search(text):
        return m.group(0)
    high = LOAN_HIGH.search(text)
    back = BACK_TO_USUAL.search(text) and not FUTURE.search(text)
    keep = KEEP_GOING.search(text)
    if high and keep and re.search(SG_DEST, text, _F) and not back:
        return f"{high.group(0)} … {keep.group(0)}"
    # the loan pays for home costs while profit or cash goes to Singapore, the pot or the set-aside
    if PAUSE_OK.search(text):
        return None
    usual = re.search(r"\bas\s+(?:usual|normal|always)\b|\blike\s+(?:every|each)\s+(?:month|year)\b|(?:usual|normal)\s+(?:level|amount)|照常|和平时一样|跟往常一样|正常水平", text, _F)  # noqa: E501
    if usual and not high and not re.search(r"\b(?:more|extra|additional|top\s+up|pull|draw\s+down)\b|多借|多贷|多提|多用", text, _F):  # noqa: E501
        return None
    for lm in re.finditer(HOME_LOAN_WORD, text, _F):
        window = text[max(0, lm.start() - 60) : lm.end() + 160]
        if (
            re.search(HOME_COST, window, _F)
            and re.search(FREED, window, _F)
            and re.search(SG_DEST, window, _F)
            and R2_LINK.search(window)
        ):
            return window.strip()
    return None


# R1, the loan stays home: loan money can't pay for anything in Singapore, the pot or the Singapore company.
# Places in Singapore the shop may be (planning areas and well-known districts).
SG_PLACE = (
    r"(?:ang\s+mo\s+kio|bedok|bishan|bugis|bukit\s+\w+|changi|chinatown|clementi|geylang|holland\s+v\w*|hougang|jurong|kallang"
    r"|marina\s+(?:bay|south|east)|novena|orchard|pasir\s+ris|paya\s+lebar|punggol|queenstown|raffles\s+place|river\s+valley"
    r"|sengkang|serangoon|tampines|tanjong\s+pagar|toa\s+payoh|woodlands|yishun|bras\s+basah|dhoby\s+ghaut|somerset|city\s+hall"
    r"|乌节|牛车水|淡滨尼|宏茂桥|裕廊|武吉|后港|盛港|榜鹅|兀兰|义顺|碧山|大巴窑|丹戎巴葛|芽笼|勿洛|金文泰|女皇镇|滨海湾|白沙浮|狮城)"
)
R1_DEST = (
    rf"(?:{SINGAPORE}|{SG_PLACE}|set-?asides?|paid-?up|share\s+capital|(?:registered|company'?s?)\s+capital|odi\s+(?:investment|amount|capital)"
    r"|investment\s+(?:amount|abroad|capital)|the\s+(?:new\s+)?outlet|over\s+there|out\s+there|那边|留存|注册资本|实缴|出资额|境外投资|投资款)"
)
R1_LOAN = (
    rf"(?:{LOAN}|facility|(?:the|this|that|our)\s+drawdown|disburse\w*|what\s+we\s+(?:drew|borrowed)|(?:drawn|drew)\s+(?:down\s+)?(?:from|on)\s+(?:webank|we\s*bank|the\s+line)"  # noqa: E501
    r"|borrowed\s+(?:rmb|yuan|cny|renminbi)|放下来的(?:款|钱)|贷出来的(?:款|钱)|放款|提款|提出来的钱|微众的钱|借的(?:款|钱))"
)
R1_LOAN_RE = re.compile(R1_LOAN, _F)
R1_DEST_RE = re.compile(R1_DEST, _F)
# the loan money going to the place: a flow word between, within one sentence
R1_FLOW = re.compile(
    r"\b(?:for|to|into|toward|towards|on|pay\w*|cover\w*|fund\w*|buy\w*|as|over|put|send|move|wire|transfer\w*|bridge|top\w*\s+up|use\w*|park|spend|cover|go(?:es)?|call)\b"  # noqa: E501
    r"|付|交|买|缴|放进|放到|补到|补进|转到|转去|转进|汇到|汇去|汇往|汇过去|打到|垫|用于|用在|用来|投到|投进|投入|充|给|拿去|作为|当作|当成|算作|出资",
    _F,
)
R1_SOURCE = re.compile(r"\b(?:from|out\s+of|with|using|off|(?:can|could|will|should|would)\s+be|is\s+just)\b|用|拿|从|出|靠|就是", _F)  # noqa: E501
SENTENCE_END = re.compile(r"[.;!?。；！？\n]")


def _r1_use(view: str) -> str | None:
    for lm in R1_LOAN_RE.finditer(view):
        for dm in R1_DEST_RE.finditer(view):
            if 0 <= dm.start() - lm.end() <= 100:
                gap, link = view[lm.end() : dm.start()], R1_FLOW
            elif 0 <= lm.start() - dm.end() <= 100:
                gap, link = view[dm.end() : lm.start()], R1_SOURCE
            else:
                continue
            if not SENTENCE_END.search(gap) and (link.search(gap) or R1_FLOW.search(gap)):
                return view[min(lm.start(), dm.start()) : max(lm.end(), dm.end())]
    return None
# spans that are not the loan going to Singapore: the loan kept at home, not used, WeBank holding the pot,
# WeBank as the lender asked for consent, repaying
R1_NOT_SPANS = [
    re.compile(
        rf"(?:(?<!why\s)\bnot|\bnever|n'?t|\bno|\bwithout|\binstead\s+of|\brather\s+than|\bnone\s+of|\bnothing\s+from)\s+(?:(?:touch|us|tap|draw|need|rely|tak|spend|com|from|on|of)\w*\s+){{0,2}}(?:any\s+(?:of\s+)?|the\s+|our\s+|my\s+|a\s+)?(?:money\s+from\s+)?(?:the\s+)?{LOAN}(?:\s+(?:money|line|loan|credit))?"  # noqa: E501
        r"|(?<!为什么)(?<!为啥)(?<!干嘛)(?<!怎么)(?:不动|不用|不碰|不是|不拿|而不是|不会用|不靠|不走|没用|不借)(?:用)?.{0,3}(?:微众|微业贷|贷款(?!行|方)|额度|借款|借来的钱)",
        _F,
    ),
    re.compile(
        rf"{LOAN}\s*(?:\w+\s+){{0,3}}?(?:stays?|kept|is\s+(?:only\s+)?for|only\s+for|just\s+for|goes\s+to|is\s+used\s+(?:only\s+)?for|funds|pays\s+for|covers|serves|for|with|on|in)\s+(?:the\s+|our\s+)?(?:home|china|domestic|shenzhen|local\s+shops|(?:\d+|thirty)\s+shops|shops\s+(?:here|at\s+home))\b(?:\s*(?:shops?|stores?|outlets?|business|side))?"  # noqa: E501
        r"|(?:微众|微业贷|贷款(?!行|方)|额度)(?:的)?(?:贷款|钱|额度)?(?:只|都|就)?(?:用在|用于|留在|给|是|放在)(?:国内|深圳|家里|这边)(?:的)?(?:门店|店|生意|业务|公司)?",
        _F,
    ),
    re.compile(
        r"(?:webank|we\s*bank|微众)(?:'s)?\s*(?:can\s+|could\s+|to\s+|will\s+)?(?:hold|keep|custod\w*|host|托管|保管|开)\w*\s.{0,30}(?:pot|sub-?account|account|储蓄|子账户|账户)"
        r"|(?:webank|we\s*bank|微众)(?:'s)?\s*(?:的)?\s*(?:\w+\s+)?(?:sub-?account|savings\s+account|account|custody|子账户|账户|托管)"
        r"|(?:pot|sub-?account|储蓄账户|子账户).{0,30}(?:at|with|in|放在|开在)\s*(?:webank|we\s*bank|微众)",
        _F,
    ),
    re.compile(CONSENT, _F),
    # the loan's level talked about (above usual, back to normal), not its use
    re.compile(
        rf"{R1_LOAN}(?:'s)?\s*(?:\w+\s+){{0,3}}?(?:balance\s+)?(?:is|'s|are|has|have|came|went|got|now|was|were)?\s*(?:\w+\s+){{0,3}}?(?:back\s+(?:down\s+)?to|at|above|over|higher|up\s+at|up\b|down\s+to|below)\s+(?:\w+\s+){{0,4}}?(?:usual|normal|level|before|average|\d[\d.,]*\s*(?:k|m|million|万)?)"  # noqa: E501
        r"|(?:微众|微业贷|贷款(?!行|方)|额度|借款)(?:的)?(?:余额)?.{0,8}(?:比平时|比往常|高于|偏高|多了|高了|降回|回到|恢复|水平|平时)",
        _F,
    ),
    re.compile(
        r"(?:repay\w*|pay(?:ing)?\s+(?:back|off|down))\s+(?:\w+\s+){0,3}?(?:webank|we\s*bank|loan|line)|loan\s+repayments?|还款|还贷"
        r"|还(?:清|上|掉|了)?.{0,6}(?:贷款|微众|微业贷|额度|借款)",
        _F,
    ),
]


# the loan placed at home (a home cost, at home, in Shenzhen): then only a flow to Singapore counts as R1
HOME_USE = re.compile(rf"{HOME_COST}|\bat\s+home\b|\b(?:in\s+china|shenzhen|domestic)\b|国内|深圳|家里", _F)


def _r1_view(text: str) -> str:
    """The message with what isn't loan money going to Singapore taken out (the loan kept home or not used,
    WeBank holding the pot or giving consent, repaying)."""
    for pat in R1_NOT_SPANS:
        text = pat.sub(" | ", text)
    return text


def r1_loan_abroad(text: str) -> str | None:
    """Loan money reaching anything in Singapore (the shop, the pot or set-aside, the Singapore company, its
    capital, the ODI investment), directly, as a bridge, mixed in or relabelled. The matched words, or
    None."""
    return _r1_use(_r1_view(text))


IN_SENTENCE = r"[^.;!?。；！？\n]"
PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "R1": [
        re.compile(rf"{LOAN}{IN_SENTENCE}{{0,40}}{SINGAPORE}", _F),
        re.compile(rf"{SINGAPORE}{IN_SENTENCE}{{0,40}}(?:use|draw|take|用|动用|提取){IN_SENTENCE}{{0,20}}{LOAN}", _F),  # noqa: E501
        re.compile(r"(?:just|only)\s+use\s+(?:my|the)\s+(?:webank\s+)?(?:line|loan|credit)", _F),
        re.compile(
            r"(?:use|draw|tap|borrow\s+(?:from|on)|take)\b.{0,15}(?:webank|we\s*bank|微业贷|my\s+(?:credit\s+)?line|the\s+line|my\s+loan)",
            _F,
        ),
        re.compile(r"(?:用|拿|先用|动用).{0,6}(?:微业贷|贷款(?!行|方)|额度)", _F),
        re.compile(
            rf"(?:draw\s*down|drawdown|draw\s+on|tap)\b{IN_SENTENCE}{{0,40}}(?:{LOAN}|(?:the|our|my)\s+(?:credit\s+)?line){IN_SENTENCE}{{0,60}}{SINGAPORE}"
            rf"|(?:draw\s*down|drawdown)\b{IN_SENTENCE}{{0,60}}{SINGAPORE}",
            _F,
        ),
    ],
    "R2": [
        re.compile(r"borrow\s+(?:more|extra).{0,60}(?:profit|cash|money).{0,30}(?:singapore|abroad|out)", _F),
        re.compile(
            r"(?:多借|多贷|借钱发工资|贷款发工资).{0,30}(?:利润|现金|钱).{0,20}(?:新加坡|出去|境外)", _F
        ),
        re.compile(
            r"(?:wages|payroll|suppliers).{0,30}(?:with|on)\s+(?:the\s+)?(?:loan|line).{0,60}(?:singapore|profit)",
            _F,
        ),
        # the loan pays the home bills so that profit can go to Singapore (indirect diversion, 置换)
        re.compile(rf"(?:{LOAN}|borrow\w*|借|贷).{{0,40}}{HOME_BILLS}.{{0,60}}{PROFIT}.{{0,40}}{SG}", _F),
        re.compile(rf"{HOME_BILLS}.{{0,40}}(?:{LOAN}|borrow\w*|借|贷).{{0,60}}{PROFIT}.{{0,40}}{SG}", _F),
        re.compile(rf"{PROFIT}.{{0,40}}{SG}.{{0,60}}(?:{LOAN}|borrow\w*|借|贷).{{0,40}}{HOME_BILLS}", _F),
    ],
    "R3": [
        re.compile(
            r"guarant|担保|保证人|作保|keep-?well|standby\s+letter|sblc|备用信用证|pledge|质押|抵押|counter-?indemn"
            r"|co-?sign|stand\s+surety|comfort\s+letter|兜底|背书|stand\s+behind|vouch\s+for|underwrite|back\s+(?:up\s+)?(?:the|their|its)\s+.{0,25}(?:loan|lease|debt)",
            _F,
        ),
    ],
    "R4": [
        # routing the money through Hong Kong (or Macau), or via a company or account there
        re.compile(rf"(?:{SEND}|{MONEY}).{{0,30}}(?:through|via|by\s+way\s+of|rout\w*|经由|经过|通过|绕道?|走)\s*.{{0,12}}{HK}", _F),  # noqa: E501
        re.compile(rf"{SEND}.{{0,25}}{MONEY}.{{0,25}}{HK}", _F),
        re.compile(rf"{HK}.{{0,15}}(?:shell|holding|holdco|account|中转|离岸|控股|账户|过一道|过一下|转一下)", _F),  # noqa: E501
        re.compile(r"(?:split|break\s+up|拆分|分拆|分开).{0,30}(?:quota|transfer|remit|额度|汇款|换汇)", _F),
        re.compile(r"(?:stay|keep(?:\s+\w+){1,2})\s+(?:under|below)\s+the\s+(?:limit|quota|radar|cap|\$?50k)", _F),  # noqa: E501
        re.compile(r"(?:分多次|分几次|分批|多次)(?:去)?(?:换汇|购汇)", _F),
        re.compile(
            r"(?:skip|avoid|without|bypass|不用|不做|跳过|绕过|免).{0,20}(?:filing|odi|备案|登记)", _F
        ),
        # money before the lender's consent, the ODI filing or the bank registration
        re.compile(
            rf"{SEND}.{{0,40}}(?:before|ahead\s+of|without\s+waiting\s+for).{{0,20}}(?:consent|filing|odi|registration|approval|paperwork)",  # noqa: E501
            _F,
        ),
        re.compile(
            rf"{SEND}.{{0,40}}(?:filing|odi|paperwork|registration|备案|登记|手续).{{0,20}}(?:later|afterwards|after|以后|之后|再补|后补|回头)",  # noqa: E501
            _F,
        ),
        re.compile(r"(?:没|未|不等)(?:有)?.{0,4}(?:备案|登记|同意|批).{0,10}(?:就|先)?.{0,6}(?:汇|转|付|打款|打钱)", _F),  # noqa: E501
        # opening, paying or investing first and the filing or registration afterwards
        re.compile(
            rf"(?:{SEND}|open|start|launch|run|operat|invest|incorporat|set\s+up|开业|开店|开起来|开张|营业|投资|注册)"
            r".{0,60}(?:filing|odi|paperwork|regist\w*|备案|登记|手续)"
            r".{0,25}(?:later|afterwards|after\b|以后|之后|再补|后补|补办|回头|再说)",
            _F,
        ),
        re.compile(r"(?:备案|登记|手续|odi).{0,12}(?:慢|等不及|来不及|麻烦|太久).{0,12}(?:先|直接).{0,10}(?:开|汇|转|付|签|投)", _F),  # noqa: E501
        re.compile(
            r"(?:employees?|staff|workers|colleagues|friends?|relatives?|family\s+members|员工|同事|朋友|亲戚|家人)"
            r".{0,30}(?:each|every\s+one|每人|各自|每个人).{0,30}(?:buy|exchange|convert|send|remit|换|购汇|汇)",
            _F,
        ),
        re.compile(r"(?:先|提前).{0,6}(?:汇|转|打)(?:钱|款|过去).{0,20}(?:备案|登记|手续)", _F),
        # the pre-investment allowance (前期费用) never pays the deposit
        re.compile(r"(?:pre-?investment|前期费用).{0,40}(?:deposit|押金)|(?:deposit|押金).{0,40}(?:pre-?investment|前期费用)", _F),  # noqa: E501
        re.compile(
            r"underground|地下钱庄|对敲|个人账户.{0,10}汇|personal account.{0,20}(?:send|remit|transfer)", _F
        ),
        # sending it personally instead of through the company's ODI
        re.compile(
            rf"{SEND}.{{0,20}}{MONEY}.{{0,30}}(?:personally|myself|from\s+my\s+(?:own|personal)\s+account|in\s+my\s+(?:own\s+)?name)",  # noqa: E501
            _F,
        ),
        re.compile(r"(?:个人名义|以个人|私人账户|自己的账户|我自己).{0,10}(?:汇|转|打)", _F),
        re.compile(r"(?:friends?|relatives?|family|朋友|亲戚).{0,20}(?:quota|额度|名义|换汇)", _F),
    ],
    "R5": [
        # running home cash below the floor
        re.compile(
            r"(?:ignore|skip|drop|forget|scrap|remove|lower|cut|don'?t\s+need|no\s+need\s+for)\s+(?:about\s+)?(?:the\s+|a\s+|any\s+)?(?:home\s+)?(?:cash\s+)?(?:floor|safety\s+(?:line|net)|buffer|reserve)",  # noqa: E501
            _F,
        ),
        re.compile(
            rf"(?:send|move|put|transfer|use|spend|throw|pour)\s+(?:all|every\s+(?:last\s+)?(?:cent|dollar|yuan)|everything)\s*(?:of\s+)?(?:our|my|the)?\s*(?:home\s+|company\s+|spare\s+)?(?:cash|reserves?|buffer)?.{{0,30}}{SG}",  # noqa: E501
            _F,
        ),
        re.compile(r"(?:不要|不管|不用|去掉|降低|取消|不留)(?:什么)?(?:安全线|底线|缓冲|备用金)", _F),
        re.compile(r"(?:全部|所有|清空|掏空)(?:的)?(?:国内)?(?:现金|流动资金|备用金|家底).{0,20}(?:新加坡|过去|出去|汇)", _F),  # noqa: E501
        re.compile(r"不留(?:底|余钱|后路|现金)", _F),
        re.compile(
            r"(?:empty|drain|clear\s+out|wipe\s+out|clean\s+out)\s+(?:the|our|my)\s+(?:home\s+|shenzhen\s+|company\s+|bank\s+)?(?:account|cash|reserves?)"  # noqa: E501
            r"|without\s+(?:a|any)\s+(?:cushion|buffer|safety\s+net|floor|reserve)",
            _F,
        ),
        re.compile(r"(?:一分钱|一分|钱)(?:都|也)?不(?:用|要|必)?留|全(?:部)?(?:投|砸|押)(?:到|去|在|进)?(?:新加坡|那边|海外|境外)", _F),  # noqa: E501
    ],
    "R6": [
        re.compile(r"sign\s+(?:the\s+)?(?:lease|offer|loi).{0,20}(?:now|first|today|before|right away)", _F),
        re.compile(
            r"(?:sign|lock\s+in|commit\s+to|put\s+down\s+the\s+deposit\s+and\s+sign)\b.{0,30}(?:lease|offer|loi|unit)"
            r".{0,30}(?:now|today|this\s+week|immediately|asap|right\s+away|without\s+waiting|before\s+the\s+(?:money|cash|funds|transfer))",  # noqa: E501
            _F,
        ),
        re.compile(r"(?:先签|现在就签|马上签).{0,10}(?:租约|合同|要约)?", _F),
        re.compile(r"先把.{0,8}签(?:了|下)|钱(?:还)?没(?:到|汇|到账).{0,12}签|签下来再(?:说|汇|筹)", _F),
    ],
    "R7": [
        re.compile(
            r"(?:personal|consumer|cash|payday)\s+loan|cash\s+advance|personal\s+credit|消费贷|个人贷款|网贷|借呗|花呗|信用卡(?:取现|套现)"
            r"|信用贷|现金贷|小额贷",
            _F,
        ),
        re.compile(r"(?:use|put|charge|take|borrow\w*|max\s+out|run\s+up)\b.{0,25}credit\s+cards?", _F),
        re.compile(r"(?:刷|用|拿)(?:我的)?信用卡", _F),
        re.compile(
            r"borrow\w*\s+(?:it\s+|money\s+|some\s+)?(?:from|off)\s+(?:my\s+|our\s+)?(?:friends?|family|relatives?|brother|sister|parents?|cousin|in-laws)",  # noqa: E501
            _F,
        ),
        re.compile(r"(?:找|向|跟)(?:朋友|亲戚|家里|父母).{0,4}借|借(?:朋友|亲戚)的钱", _F),
    ],
    "R8": [
        # a Singapore bank, and borrowing from it or asking it for money
        re.compile(rf"{SG_BANK}.{{0,40}}{BORROW}|{BORROW}.{{0,40}}{SG_BANK}", _F),
        re.compile(
            rf"(?:ask|approach|apply\s+(?:to|at|with)|go\s+to|get\s+(?:money|cash|funds|it|the\s+rest)\s+from)\s+(?:a\s+|the\s+|our\s+)?(?:\w+\s+)?{SG_BANK}"
            rf"|(?:找|向|跟|问){SG_BANK}.{{0,10}}(?:要|拿|申请|弄)",
            _F,
        ),
        # another Singapore lender
        re.compile(SG_LENDER, _F),
        # EFS, Enterprise Singapore's loans or grants, other government SME loans
        re.compile(EFS, _F),
        # a loan or financing in Singapore, there, locally, or taken by the Singapore company
        re.compile(
            r"(?:loans?|borrow\w*|financ\w*|credit\s+(?:line|facility)|overdraft|lend\w*)\s+(?:\w+\s+){0,4}?(?:in|from|at|with)\s+(?:a\s+|the\s+)?(?:singapore|(?<![a-z])sg(?![a-z]))"
            r"|(?:singapore|(?<![a-z])sg(?![a-z]))(?:'s)?\s+(?:bank\s+|business\s+|sme\s+|company\s+|side\s+)?(?:loans?|financing|borrowing|credit\s+(?:line|facility)|overdraft)"
            r"|borrow\w*\s+(?:\w+\s+){0,3}?(?:locally|over\s+there|out\s+there|there\b)"
            r"|local\s+(?:loans?|financing|borrowing|lenders?|credit)"
            r"|(?:singapore|(?<![a-z])sg(?![a-z]))\s+(?:company|entity|subsidiary|pte(?:\s+ltd)?|side|shop)\b.{0,30}(?:borrow|take\s+(?:out\s+)?(?:a\s+|the\s+)?loan|get\s+(?:a\s+|the\s+)?loan|apply\s+for|financ)"
            r"|\bpte\.?\s+ltd\b.{0,30}(?:borrow|loan|financ)",
            _F,
        ),
        re.compile(
            r"(?:在|去|从|找|向|跟|用|问)(?:新加坡|狮城|当地|本地|那边|那里)(?:的)?.{0,10}(?:贷|借|融资|透支|分期|授信)"
            r"|(?:新加坡|狮城|当地|本地|那边)(?:的)?(?:贷款|借款|融资|信贷|透支|银行贷|银行借)"
            r"|新加坡(?:公司|主体|子公司|那边的公司).{0,10}(?:贷|借|融资)",
            _F,
        ),
    ],
}

# R8 only flags a plan to borrow in Singapore *before opening*. The plan is made before opening, so a request
# counts as before opening unless it says the borrowing comes after opening (and names no pre-opening cost).
R8_PRE = re.compile(
    r"before\s+(?:we\s+|the\s+shop\s+|it\s+)?open|pre-?opening|deposit|fit-?out|renovat|set-?up|start-?up\s+costs?|to\s+get\s+(?:started|going)"
    r"|开业前|开店前|开张前|押金|装修|前期|筹备|启动",
    _F,
)
# A question about eligibility or what's needed (no request in it) is learning about R8, not relying on it.
R8_INFO = re.compile(
    r"\b(?:does|do|is|are|would)\b[^.!。！]{0,60}\b(?:need|require[sd]?|qualify|eligible|count)\b"
    r"|需要.{0,20}(?:吗|么)|(?:条件|资格|要求)(?:是什么|有哪些)|符合.{0,10}(?:吗|条件)|够不够格",
    _F,
)


# Asking about a rule or its risk isn't requesting a breach: a question to learn stays quiet unless it
# also carries a request ("what's the risk if we just use the loan?").
ASKING = re.compile(
    r"\b(?:what(?:'s|\s+is|\s+are)\s+the\s+risks?|risks?\s+of|explain|help\s+me\s+understand|tell\s+me\s+about"
    r"|what\s+does\s+.{0,40}\s+mean|why\s+(?:can'?t|can\s+we\s+not|is\s+it|isn'?t|do\s+(?:i|we)\s+need|does))"
    r"|了解|请问|解释|什么意思|为什么|(?:有|是)(?:什么|哪些)风险|风险(?:是什么|有哪些|大不大|大吗|有多大)|的风险",
    _F,
)
# what a rule means or what it covers: quiet unless the rest of the message (the rule's name taken out) pushes
RULE_NAME = re.compile(
    r"(?:'|\"|“|‘|「)?(?:legal\s+order|cash\s+before\s+commitment|pre-?investment\s+allowance|前期费用|法定顺序|先到账[，,]?\s*再签约|(?<![a-z])R[1-8](?![0-9])|(?:this|the|that)\s+rule|这条(?:规定|规则)?|这个规定|这项规定)(?:'|\"|”|’|」)?",  # noqa: E501
    _F,
)
RULE_QUESTION = re.compile(
    r"\b(?:what\s+(?:is|are|does)|explain|meaning\s+of|what\s+can\s+it|what\s+.{0,20}\s+(?:cover|mean))\b|怎么理解|指什么|是什么意思|什么意思|具体指|能用来(?:干|做)什么|包括(?:什么|哪些)|是什么",  # noqa: E501
    _F,
)
REQUESTING = re.compile(
    r"\b(?:let'?s|we'?ll|i'?ll|we\s+will|i\s+will|can\s+(?:we|i)|could\s+(?:we|i)|should\s+(?:we|i)|just|go\s+ahead"
    r"|want\s+to|going\s+to|plan\s+to|anyway|still|how\s+about|why\s+not|why\s+don'?t\s+(?:we|i))\b"
    r"|帮我|我要|我们要|打算|准备|直接|吧|先|就|让|还是|照样|为什么不(?!能|可以|行|允许)",
    _F,
)


@dataclass(frozen=True)
class Intent:
    rule_id: str
    matched: str


def classify(text: str) -> list[Intent]:
    if ASKING.search(text) and not REQUESTING.search(text):
        return []
    if RULE_NAME.search(text) and RULE_QUESTION.search(text) and not REQUESTING.search(RULE_NAME.sub("", text)):  # noqa: E501
        return []
    hits: list[Intent] = []
    sg_borrowing = any(pat.search(text) for pat in PATTERNS["R8"])
    r1_view = _r1_view(text)
    for rule_id, pats in PATTERNS.items():
        for pat in pats:
            if rule_id == "R1" and HOME_USE.search(r1_view):
                break  # the loan is placed at home: r1_loan_abroad decides from the flow
            m = pat.search(r1_view if rule_id == "R1" else text)
            if m:
                if rule_id == "R8" and (
                    (R8_AFTER.search(text) and not R8_PRE.search(text))
                    or (R8_INFO.search(text) and not REQUESTING.search(text))
                ):
                    continue  # borrowing after opening is a lawful option; asking who qualifies is learning
                if rule_id == "R4" and r4_all_done(text):
                    continue  # every step is done: the money may go
                if rule_id == "R6" and r6_money_in(text):
                    continue  # all the money is in Singapore: signing is the next lawful step
                hits.append(Intent(rule_id, m.group(0)))
                break
    found = {h.rule_id for h in hits}
    if "R4" not in found and (matched := r4_order(text)):
        hits.append(Intent("R4", matched))
    if "R6" not in found and (matched := r6_commit(text)):
        hits.append(Intent("R6", matched))
    if "R2" not in found and (matched := r2_free_profit(text)):
        hits.append(Intent("R2", matched))
    if "R1" not in found and (matched := r1_loan_abroad(text)):
        hits.append(Intent("R1", matched))
    # A Singapore loan is R8's question, not R1's, unless the home loan is named ("WeBank", "our loan").
    if sg_borrowing and not WEBANK.search(r1_view) and not HOME_LOAN.search(r1_view):
        hits = [h for h in hits if h.rule_id != "R1"]
    # A guarantee mention with no link to borrowing or Singapore (e.g. "product guarantee") isn't R3.
    if any(h.rule_id == "R3" for h in hits) and not re.search(
        rf"{LOAN}|{SINGAPORE}|公司|company|我", text, _F
    ):
        hits = [h for h in hits if h.rule_id != "R3"]
    return hits


# ------------------------------------------------------------------ topics

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "T-RESIDENT-DIRECTOR": [r"director", r"董事", r"nominee"],
    "T-EP-SALARY": [r"employment pass", r"\bep\b", r"work pass", r"visa", r"准证", r"签证", r"店长"],
    "T-CPF-QUOTA": [r"\bcpf\b", r"公积金", r"quota", r"配额", r"foreign workers?", r"外籍"],
    "T-GST": [r"\bgst\b", r"消费税", r"tax on", r"税"],
    "T-GTO": [r"\bgto\b", r"turnover rent", r"营业额租金", r"分成"],
    "T-STATION-TRAFFIC": [r"footfall", r"foot traffic", r"人流", r"客流", r"mrt", r"地铁"],
    "T-NOT-YET-SIGN": [r"sign", r"offer", r"\bloi\b", r"签约", r"要约", r"订下", r"lock (?:it|in)"],
    "T-REINSTATEMENT": [r"reinstat", r"restore", r"复原", r"退租"],
    "T-WEBANK-ROLE": [
        r"webank.{0,20}(?:role|do|help)",
        r"微众.{0,10}(?:作用|角色|帮)",
        r"why not.{0,20}loan",
    ],
    "T-LENDER-CONSENT": [r"consent", r"同意", r"permission from (?:the )?bank"],
    "T-ODI": [r"\bodi\b", r"filing", r"备案", r"drc", r"发改委", r"商务局"],
    "T-PRE-INVESTMENT": [r"前期费用", r"pre-?investment", r"before the company"],
    "T-SAFETY-FLOOR": [r"safety line", r"floor", r"安全线", r"why.{0,20}grey", r"灰色"],
    "T-PARTNER": [r"partner", r"合伙", r"股东", r"local (?:pr|citizen)"],
    "T-HIRING-LOCALS": [r"staff", r"crew", r"hire", r"hiring", r"workers? from (?:china|shenzhen)", r"员工", r"招聘", r"带人", r"团队", r"工作准证"],  # noqa: E501
}
_TOPIC_RES = {k: re.compile("|".join(v), _F) for k, v in TOPIC_KEYWORDS.items()}
_QUESTION = re.compile(r"\?|？|what|why|how|do i|need|吗|么|什么|为什么|怎么|是否|需不需要|要不要", _F)


def match_topic(text: str, allowed: list[str]) -> str | None:
    """A side question about a known topic. Only questions count, and only topics the Skill allows."""
    if not _QUESTION.search(text):
        return None
    for topic_id in allowed:
        pat = _TOPIC_RES.get(topic_id)
        if pat and pat.search(text):
            return topic_id
    return None


# ------------------------------------------------------------------ "this step is done" (SPEC §7.4)

DONE = re.compile(
    r"\b(?:done|finished|complete[d]?|got|received|came through|approved|signed|sent|filed|registered|incorporated|opened|released|transferred)\b"  # noqa: E501
    r"|已完成|完成了|办完|办好|搞定|拿到|收到|批了|同意了|签了|已签|已提交|已备案|已登记|注册好|开好|已汇出|汇出了|开业了",
    _F,
)
MILESTONE_WORDS: dict[str, re.Pattern[str]] = {
    "lender_consent": re.compile(r"consent|lender|贷款行|银行同意|同意函|同意申请", _F),
    "odi_filing": re.compile(r"\bodi\s+filing|filing|\bdrc\b|commerce bureau|备案|发改委|商务局", _F),
    "bank_registration": re.compile(r"(?:bank|odi)\s+registration|外汇登记|银行登记", _F),
    "incorporate": re.compile(r"incorporat|pte\s*ltd|company (?:is )?registered|bank account|注册公司|新加坡公司注册|开户", _F),  # noqa: E501
    "setup_transfer": re.compile(r"setup transfer|set-up transfer|设立资金", _F),
    "first_transfer": re.compile(r"first (?:main )?transfer|main transfer|首笔", _F),
    "sign_lease": re.compile(r"lease|letter of offer|租约|租赁合同", _F),
    "hiring": re.compile(r"hir(?:ed|ing)|staff|招聘|员工", _F),
    "fitout": re.compile(r"fit-?out|renovation|装修", _F),
    "licence": re.compile(r"licen[cs]e|\bsfa\b|执照|许可证", _F),
    "opening": re.compile(r"\bopen(?:ed)? the shop|shop (?:is )?open|开业", _F),
}


def milestone_done(text: str) -> str | None:
    """Code reading of "<step> is done" when no model is available: exactly one step named, plus a
    done word. It only proposes; the caller validates the order and asks the owner to confirm."""
    if not DONE.search(text):
        return None
    hits = [mid for mid, pat in MILESTONE_WORDS.items() if pat.search(text)]
    return hits[0] if len(hits) == 1 else None
