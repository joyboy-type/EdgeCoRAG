"""Create the canonical portable report input from verified saved-run diagnostics."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/v1.10.1/diagnostics'

def build():
    r=json.loads((OUT/'diagnostic_results.json').read_text())
    now=datetime.now(timezone.utc).isoformat()
    models=['qwen3vl_4b','qwen3vl_8b','gemma4_e2b','gemma4_e4b','qwen35_4b']
    def ordered(rows):return sorted(rows,key=lambda x:models.index(x['model_key']))
    gt=ordered([x for x in r['gt_decomposition'] if x['split']=='frozen_test'])
    errors=ordered([x for x in r['condition_errors'] if x['split']=='frozen_test' and x['condition']=='S2'])
    error_long=[]
    for x in errors:
        for field,label in [('valid_choice_wrong','有效选项但答错'),('format_failures','格式失败')]:
            error_long.append({**x,'error_type':label,'count':x[field],'rate':x[field]/x['n']})
    summary=ordered([x for x in r['summary'] if x['split']=='frozen_test'])
    for x in summary:x['all_three_wrong_rate']=x['all_three_wrong']/x['n']
    format_rows=[x for x in r['format_decomposition'] if x['split']=='frozen_test' and x['model_key']=='qwen35_4b' and x['left']=='S1' and x['right']=='S2']
    names={'both_parse_ok':'两条件格式均有效','right_only_format_failure':'仅S2格式失败','left_only_format_failure':'仅S1格式失败','both_format_failure':'两条件格式均失败'}
    for x in format_rows:x['group_label']=names[x['format_group']]
    cases=[]
    for x in r['selected_cases']:
        if x['category']!='hash_hit_s1_wrong_s2_correct':continue
        cases.append({**x,'S0':x['S0_raw'].strip(),'S1':x['S1_raw'].strip(),'S2':x['S2_raw'].strip(),'review_status':'仅记录核验，未看图审定'})
    datasets={'gt':gt,'oracle_errors':error_long,'error_bounds':errors,'summary':summary,'format_bridge':format_rows,'cases':cases}
    blocks=[]
    def md(id,body,source=None):
        block={'id':id,'type':'markdown','body':body}
        if source:block['sourceId']=source
        blocks.append(block)
    def cb(id):blocks.append({'id':id+'_block','type':'chart','chartId':id})
    def tb(id):blocks.append({'id':id+'_block','type':'table','tableId':id})
    title='EdgeCoRAG 已保存结果诊断'
    md('title','# '+title)
    md('summary','## 检索变化与格式失败只能解释部分差距\n\n本轮对齐了 **5.9k 个“问题×模型”单元、17.7k 条主条件回答**；内部留出与冻结测试分开，不把模型、条件或重复运行当独立问题。S0仅查询图，S1是发布候选top3，S2是actual GT条件。\n\n冻结集每模型固定 **1033题**。Qwen3-VL 4B 的S1相对S0净少答对26题，来自无GT哈希命中组的−30题与命中组的+4题。Gemma E2B/E4B在S2仍错592/540题，且该条件格式失败为0。**这支持继续研究证据使用与模型能力边界；不能直接判定具体视觉或推理原因。**','diagnostic')
    md('definitions','## 这里的命中和错误分别指什么\n\nGT哈希命中只表示实际送入的top3中，至少有一张图片与GT图片的JPEG95字节SHA完全相同。冻结集命中组516题，未命中组517题；没有语义支持性判定，不能把未命中直接称为检索失败。\n\n严格正确率以完整题单为分母，格式失败始终计错。下面的贡献百分点都除以完整1033题，两个GT分组可以相加回总体变化；并非剔除失败后的成功子集分数。全部为结果后的描述性分析，没有新增推理或调整参数。','diagnostic')
    md('gt_finding','## 四个模型在无GT哈希命中组出现净退步\n\nQwen3-VL 4B、8B、Gemma E2B和Qwen3.5在未命中组的S1−S0分别为−30、−23、−14、−14题；Gemma E4B是例外，为+6题。五模型的命中组均有正向净变化，但这不构成“命中导致提升”的因果证明。\n\nGT组是离线按标注分的组，题目难度和场景构成可能不同；并且图片哈希未命中不排除语义相关证据。下一步应据此安排看图审查，而不是直接给每题贴检索失败标签。','diagnostic')
    cb('gt_contributions');tb('gt_values')
    md('oracle_finding','## Gemma的GT条件错误主要是有效选项答错\n\nGemma E2B在S2答错592/1033题（57.31%），E4B答错540/1033题（52.27%），这些输出都能按原规则抽出有效选项。两模型在三个条件均错的题分别有469和437道；现有记录因此不能把主要质量差距归因于格式问题。\n\nS2包含GT证据，但不保证每题可解或标注无歧义；也可能涉及视觉读取、知识、证据利用、上下文数量等因素。没有原图核验时，这些仍是待检验解释。','diagnostic')
    cb('oracle_error_rates');tb('pattern_summary')
    md('format_finding','## Qwen3.5的格式失败压低收益，但不能填平全部差距\n\n冻结集Qwen3.5的S2比S1净多答对38题。按两条件格式状态互斥拆分：均有效组贡献+56题，仅S2失败组−25题，仅S1失败组+7题，两边均失败组0题。四组仍使用完整1033题为分母。\n\n正式主条件99次格式失败中，98次记录了64token预算耗尽。这是同时发生的记录特征，不能证明增加预算必定改善，也不允许事后改评分或只报告较好版本。','diagnostic')
    tb('format_bridge_values')
    md('bound_finding','## 即便把Qwen3.5的S2格式错误全算对也只有63.50%\n\n这个极端上限是假定55次格式失败全部正确、其他回答不变，得到656/1033；仍低于Qwen3-VL 4B原始S2的717/1033（69.41%），相差61题。它仅约束“只补回格式错误最多能改多少分”，**不是恢复后的准确率，不是重评分，也不是新预算实验的预测。**\n\n所有原始准确率保持原样。不能从格式有效子集的较高分数反推整体质量已改善。','diagnostic')
    tb('error_bound_values')
    md('case_finding','## 哈希命中仍可能伴随S1错误和S2正确\n\n冻结集这种情况在五模型分别有47、44、58、53、37题。哈希命中只保证至少一张GT图片相同，不保证GT集合完整、证据位置相同或其他干扰内容一致；因此不能仅据此判定“看到了但不会用”。\n\n下表每模型展示一个按固定SHA排序选出的事后案例；完整20例涵盖四类记录模式，另附问题文本、选项和原始回答。它们没有接受看图机制审定，也不代表总体发生率。','diagnostic')
    tb('record_cases')
    md('method','## 配对设计与复算核对\n\n只取quality阶段S0/S1/S2，内部留出每模型150题，冻结每模型1033题。S3的62条正式回答及全部开发、smoke、性能与warmup不进入本诊断。逐题校验模型revision、答案与场景一致、查询图一致及五模型证据顺序一致。\n\n原解析器重算每条输出；八种S0/S1/S2正确性模式互斥穷尽。GT分组和格式状态分别进行精确可加的净答对数拆解，并用独立SQLite查询从逐题事实表对账，最后与原quality表和转移表逐项核对。伴随笔记本可从公开压缩记录重新执行。没有新置信区间或显著性检验。','diagnostic')
    md('limitations','## 原因判断仍停在待审层面\n\n本报告按你的选择只做现有记录诊断，未核验正式题目的原图；自动记录标签不等于人工或视觉语义审定。所有机制字段保持未审定。\n\n数据同源且跨split存在图片相关性，冻结集有已披露审计暴露；事后分组、选例和分解都属探索性描述。S1与S2证据数量不同，不能把两者差值全部归为证据质量。GT未命中不等于无用，GT命中不等于语义支持充分，GT条件答错不等于纯推理不足。')
    md('next','## 下一步先审定记录指向的案例\n\n1. 已有结果足以补写阶段报告中的诊断与局限，无需重新租卡。\n2. 若继续判定机制，先取得固定版本原图并对选定案例制定审阅规则，逐项核对图像读取、GT充分性、干扰和问题歧义；不调整本轮prompt、64token或解析器。\n3. 来源分组和第二数据集仍是独立待办。只有事先冻结新的补充实验范围后，再安排GPU。')
    md('questions','## 还有哪些问题不能由记录回答\n\n- GT哈希未命中的图片是否仍提供语义上有用的证据？\n- 命中GT但S1答错的题，差异来自其他证据、图像数量、顺序还是识别能力？\n- 更长预算是否改善格式与质量？这需要单独版本的预先设定实验，不能从耗尽标记直接推出。')
    sources=[{'id':'diagnostic','label':'已保存输出的事后记录诊断','path':'reports/v1.10.1/diagnostics/diagnostic_results.json',
        'query':{'engine':'Python 3 standard library + in-memory SQLite','language':'python','executed_at':now,
        'description':'analysis/v1.10.1/diagnose_saved_runs.py compute(): strict parser validation, exact paired pattern and contribution decomposition; SQL reconciled from row facts.',
        'filters':['stage=quality','condition in S0/S1/S2','split kept separate','no new inference; no image adjudication'],
        'metric_definitions':{'unit':'one split/model/qid with three paired outputs; 5915 units are not 5915 independent questions',
        'accuracy':'strict correct / full fixed split denominator','format_ceiling':'(correct + format_failures) / n, hypothetical fixed-record bound only'}}}]
    for sid,label,sqlname,path in [('gt_source','GT哈希分组对总体变化的贡献','gt_decomposition','gt_decomposition.csv'),
                                 ('format_source','格式状态的互斥分解','format_decomposition','format_decomposition.csv')]:
        sources.append({'id':sid,'label':label,'path':'reports/v1.10.1/diagnostics/'+path,
            'query':{'engine':'SQLite in memory','language':'sql','sql':r['sql_queries'][sqlname],
            'tables_used':['triples'] if sid=='gt_source' else ['contrasts'],'executed_at':now,
            'description':'Queries actually executed against row-grain facts; contribution pp = net_correct_change / full split n * 100 in Python.',
            'filters':['quality main conditions only','frozen_test for visible chart/table'],
            'metric_definitions':{'n':'paired questions in the mutually exclusive group','contribution_pp_full_denominator':'100 * net_correct_change / 1033'}}})
    sources.append({'id':'errors_source','label':'严格错误类别与极端格式上限','path':'reports/v1.10.1/diagnostics/condition_errors.csv',
                    'query':{'engine':'SQLite in memory','language':'sql','sql':r['sql_queries']['condition_errors'],'tables_used':['condition_runs'],'executed_at':now,
                    'description':'Saved outputs validated with strict_choice_v1; valid wrong = n - correct - format_failures. No relaxed extraction or rescoring.',
                    'filters':['frozen_test','condition=S2'],'metric_definitions':{'rate':'count / full denominator 1033','ceiling':'hypothetical (correct+format_failures)/1033, not recovered accuracy'}}})
    sources.append({'id':'cases_source','label':'事后固定规则选出的记录案例','path':'reports/v1.10.1/diagnostics/selected_cases.csv',
                    'query':{'engine':'SQLite in memory','language':'sql','sql':r['sql_queries']['selected_cases'],'tables_used':['review_candidates'],'executed_at':now,
                    'description':'Per model/category choose minimum SHA256(42|model|category|qid), avoiding duplicate qids within each model. Main table shows hash-hit S1-wrong S2-correct category only.',
                    'filters':['frozen_test','one case per model/category','visual_review_completed=false'],
                    'metric_definitions':{'pattern':'S0,S1,S2 strict correctness bits; not a causal diagnosis'}}})
    sources.append({'id':'summary_source','label':'三条件逐题模式汇总','path':'reports/v1.10.1/diagnostics/summary.csv',
                    'query':{'engine':'SQLite in memory','language':'sql','sql':r['sql_queries']['record_summary'],'tables_used':['triples'],'executed_at':now,
                    'description':'Independent aggregation from all split/model/qid triples, reconciled with Python; main report filters frozen_test.',
                    'filters':['stage=quality','main S0/S1/S2 paired units','frozen_test in visible table'],
                    'metric_definitions':{'all_three_wrong':'count of strict correctness pattern 000','s1_wrong_s2_correct':'sum(s1=0 AND s2=1)'}}})
    def chart(id,title,dataset,y,series,description,source):
        return {'id':id,'title':title,'description':description,'showDescription':True,'type':'horizontalBar',
                'intent':'comparison','question':title,'rationale':'Grouped bars compare five models with two meaningful outcome groups; signed contribution preserves zero baseline.',
                'dataset':dataset,'sourceId':source,'encodings':{'x':{'field':'model'},'y':{'field':y},'color':{'field':series}},
                'options':{'grouping':'grouped'},'legend':{'show':True,'position':'bottom'},'palette':{'kind':'categorical'}}
    charts=[chart('gt_contributions','GT哈希分组对S1相对S0变化的贡献','gt','contribution_pp_full_denominator','group',
                  '冻结集每模型1033题；单位百分点；命中516题、未命中517题；两组可相加回总体差值。','gt_source'),
            chart('oracle_error_rates','S2条件下的错误类别','oracle_errors','rate','error_type',
                  '冻结集错误数除以固定1033题；有效选项答错与格式失败分别展示。','errors_source')]
    charts[1]['valueFormat']='percent'
    tables=[]
    def table(id,title,dataset,columns,source,sortfield,description):
        tables.append({'id':id,'title':title,'description':description,'showDescription':True,'dataset':dataset,'sourceId':source,
                       'columns':[{'field':f,'label':l} for f,l in columns],
                       'defaultSort':{'field':sortfield,'direction':'asc'},'density':'spacious'})
    table('gt_values','GT分组净变化核对','gt',[('model','模型'),('group','分组'),('n','题数'),('improvements','错转对'),('regressions','对转错'),('net_correct_change','净答对变化')],
          'gt_source','model','所有组保留固定题目；这不是独立检索R@k或语义支持率。')
    table('pattern_summary','记录模式与GT条件错误','summary',[('model','模型'),('all_three_wrong','三条件均错'),('s1_wrong_s2_correct','S1错S2对'),('s1_wrong_s2_correct_with_gt_hash_hit','其中命中GT哈希'),('s2_wrong','S2仍错')],
          'summary_source','model','每模型分母1033；列之间有重叠，不能相加为互斥错误类别。八种互斥模式另附CSV。')
    table('format_bridge_values','Qwen3.5从S1到S2的格式状态分解','format_bridge',[('group_label','互斥组'),('n','题数'),('improvements','错转对'),('regressions','对转错'),('net_correct_change','净答对变化')],
          'format_source','group_label','四组覆盖全部1033题，净变化相加为+38题。')
    bound_rows=[]
    for x in errors:bound_rows.append({**x,'strict_text':f"{100*x['strict_accuracy']:.2f}%",'ceiling_text':f"{100*x['all_format_failures_assumed_correct_ceiling']:.2f}%"})
    datasets['error_bounds']=bound_rows
    table('error_bound_values','原分数与极端格式上限','error_bounds',[('model','模型'),('correct','原正确题数'),('format_failures','格式失败'),('strict_text','严格准确率'),('ceiling_text','全补对假想上限')],
          'errors_source','model','假想上限只用于界定格式错误可能影响的最大分数，不是新测量或可达到的质量。')
    table('record_cases','哈希命中但S1错误的记录案例','cases',[('model','模型'),('qid','题目ID'),('gold','正确项'),('S0','S0输出'),('S1','S1输出'),('S2','S2输出')],
          'cases_source','model','全部为事后规则选例；原始题干、选项与回答在配套CSV，未进行看图审定。')
    artifact={'surface':'report','manifest':{'version':1,'surface':'report','title':title,'description':'固定运行结果的事后诊断；仅记录核验，无新增推理或视觉机制结论。',
                 'generatedAt':now,'blocks':blocks,'charts':charts,'tables':tables,'sources':sources},
              'snapshot':{'version':1,'generatedAt':now,'status':'ready','datasets':datasets}}
    (OUT/'artifact.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    (OUT/'report_source_notes.json').write_text(json.dumps({'delivery_mode':'portable_html','audience':'technical',
        'reason':'The continuing user-selected local file and GitHub delivery; scientific diagnostic methodology is the report purpose.',
        'technical_structure':'summary; definitions and findings; paired design; limitations; next steps; further questions',
        'chart_plan':[{'id':'gt_contributions','family':'grouped signed bars','purpose':'exact additive contribution by GT hash group','scale':'pp over full n=1033'},
                      {'id':'oracle_error_rates','family':'grouped bars','purpose':'valid wrong vs format failures, full-denominator shares','scale':'fractional rates'}],
        'same_chart_family_reason':'Both findings compare the same five models under a binary diagnostic grouping; no temporal trend is implied.',
        'source_file_hashes':{name:__import__('hashlib').sha256((ROOT/name).read_bytes()).hexdigest() for name in ['logs/B_predictions.jsonl.gz','logs/B_input_contexts.jsonl.gz','analysis/v1.10.1/diagnose_saved_runs.py']},
        'visual_adjudication':'not performed; user selected saved-record analysis only'},ensure_ascii=False,indent=2)+'\n')
    return artifact

if __name__=='__main__':
    artifact=build();print(json.dumps({'blocks':len(artifact['manifest']['blocks']),'charts':len(artifact['manifest']['charts']),
                                    'tables':len(artifact['manifest']['tables']),'snapshot_rows':sum(len(x) for x in artifact['snapshot']['datasets'].values())}))
