"""P7 finite private candidate pipeline and pure fact authentication."""
import copy
import traceback
from datetime import datetime, timezone

import curve_project as m
import curve_candidates as completion
import curve_bridges as bridge
import curve_connections as connection
import curve_final as final
import curve_final_render as audio

REV = final.REV
REQUEST_FIELDS = 'schema spec_rev contract_rev token input_project input_contract_rev input_fingerprint scope target_gaps mode seed parameters algorithm_version request_fingerprint'
OUTCOME_FIELDS = 'schema spec_rev contract_rev request_fingerprint status candidates facts stage_bundle search insufficient_reason failures error outcome_fingerprint'


def request_fingerprint(value):
    return m.digest('emoblocks.recommendation-request.v1',{k:v for k,v in value.items() if k!='request_fingerprint'})


def outcome_fingerprint(value):
    return m.digest('emoblocks.recommendation-outcome.v1',{k:v for k,v in value.items() if k!='outcome_fingerprint'})


def parameters(values=None):
    result=dict(completion_budget=dict(completion.BUDGET),bridge_parameters=bridge.parameters(),
        connection_parameters=connection.parameters(),boundary_parameters=final.parameters(),max_pipeline_candidates=4,max_recommendations=2)
    if values is not None:
        if not isinstance(values,dict) or set(values)-set(result): m.reject('推荐参数不受支持。','INVALID_PARAMETERS')
        result.update(values)
    budget = dict(completion.BUDGET)
    if not isinstance(result['completion_budget'], dict) or set(result['completion_budget'])-set(budget): m.reject('补全预算不受支持。')
    budget.update(result['completion_budget'])
    for key, value in budget.items(): m.integer(value, 1, completion.LIMITS[key])
    result['completion_budget'] = budget
    result['bridge_parameters']=bridge.parameters(result['bridge_parameters'])
    result['connection_parameters']=connection.parameters(result['connection_parameters'])
    result['boundary_parameters']=final.parameters(result['boundary_parameters'])
    m.integer(result['max_pipeline_candidates'],1,8);m.integer(result['max_recommendations'],1,4)
    return result


def make_request(project,token,selected_gap_id=None,seed=31,values=None,mode=None):
    m.validate(project);m.integer(seed,0,2**32-1)
    p=parameters(values);base=completion.make_request(project,selected_gap_id,seed,p['completion_budget'])
    if token['input_fingerprint']!=m.fingerprint(project) or token['project_id']!=project['project_id'] or token['contract_rev']!=REV: m.reject('推荐输入身份不匹配。','STALE_SNAPSHOT')
    mode=mode or ('melody_only' if project['settings']['melody_only'] else 'arranged')
    if mode not in ('melody_only','arranged'): m.reject('推荐模式不受支持。')
    value=dict(final.header('emoblocks.recommendation-request.v1'),token=copy.deepcopy(token),input_project=copy.deepcopy(project),
        input_contract_rev=project['contract_rev'],input_fingerprint=m.fingerprint(project),scope='selected' if selected_gap_id else ('all' if base['target_gaps'] else 'current_complete'),
        target_gaps=copy.deepcopy(base['target_gaps']),mode=mode,seed=seed,parameters=p,algorithm_version='curve-recommendation-v1')
    value['request_fingerprint']=request_fingerprint(value);return value


@final.guard
def validate_request(request):
    m.shape(request,REQUEST_FIELDS);final.version(request,'emoblocks.recommendation-request.v1')
    selected=request['target_gaps'][0]['id'] if request['scope']=='selected' else None
    expected=make_request(request['input_project'],request['token'],selected,request['seed'],request['parameters'],request['mode'])
    if expected!=request: m.reject('推荐快照、目标或参数被改变。','STALE_SNAPSHOT')


def fact(kind,data,dependencies=()):
    if kind=='application': ref=dict(id=data['transaction_id'],version=1,fingerprint=m.digest('emoblocks.application.v1',data))
    else: ref=final.ref(data)
    return dict(id=ref['id'],kind=kind,version=ref['version'],fingerprint=ref['fingerprint'],data=copy.deepcopy(data),dependencies=copy.deepcopy(list(dependencies)))


def index_facts(facts):
    if len(facts)>2048: m.reject('候选事实数量超过上限。')
    return m.indexed(facts)


def resolve(facts,ref,kind=None):
    values=facts if isinstance(facts,dict) else index_facts(facts)
    row=values.get(ref['id'])
    if row is None or (row['version'],row['fingerprint'])!=(ref['version'],ref['fingerprint']) or kind and row['kind']!=kind:
        m.reject('乐谱依赖缺失或版本不匹配。','PLAN_VERSION_MISMATCH')
    return row['data']


@m.validated_operation
def validate_facts(facts, stage_bundle=None, owned_ids=None):
    rows=index_facts(facts);seen=set();visiting=set()
    def visit(ident,depth=0):
        if depth>32 or ident in visiting: m.reject('乐谱事实引用有环或超过深度上限。')
        if ident in seen:return
        row=rows[ident];m.shape(row,'id kind version fingerprint data dependencies');visiting.add(ident)
        for dep in row['dependencies']:
            resolve(rows,dep);visit(dep['id'],depth+1)
        data=row['data'];kind=row['kind']
        if kind=='boundary_request':
            final.validate_request(data)
            parent_refs=[]
            for project in (data['connection_ref']['request']['input_project'],data['actual_layout']['base_project']):
                for record in project['records']:
                    overlay=record['payload'].get('p7') if record['kind']=='final_score' else None
                    if overlay:
                        source=resolve(rows,overlay['score_ref'],'final_score')
                        if source!=overlay['final_score']:m.reject('原输入接受谱与来源registry不同。','SOURCE_CLOSURE_INVALID')
                        if overlay['score_ref'] not in parent_refs:parent_refs.append(overlay['score_ref'])
            if any(ref not in row['dependencies'] for ref in parent_refs):m.reject('边界请求未登记已接受来源依赖。','SOURCE_CLOSURE_INVALID')
            if stage_bundle is not None and (owned_ids is None or ident in owned_ids):
                attempt=next((a for a in stage_bundle['attempts'] if a['id']==data['connection_ref']['attempt_id']),None)
                if attempt is None or attempt['state']!='READY' or attempt['connection']['request']!=data['connection_ref']['request'] or attempt['connection']['plan']!=data['connection_ref']['plan'] or attempt['connection']['results']!=data['connection_ref']['results'] or attempt['connection']['outcome']!=data['connection_ref']['outcome']:
                    m.reject('最终事实没有对应真实就绪连接暂存。','CONNECTIONS_NOT_READY')
        elif kind=='boundary_plan':
            request=next((r['data'] for r in rows.values() if r['kind']=='boundary_request' and final.request_fingerprint(r['data'])==data['request_fingerprint']),None)
            if request is None:m.reject('最终计划缺少原请求。')
            if final.ref(request) not in row['dependencies']:m.reject('最终计划未登记请求依赖。')
            final.validate_plan(request,data)
        elif kind=='boundary_result':
            plan=resolve(rows,data['plan_ref'],'boundary_plan')
            request=next(r['data'] for r in rows.values() if r['kind']=='boundary_request' and final.request_fingerprint(r['data'])==data['request_fingerprint'])
            if any(dep not in row['dependencies'] for dep in (final.ref(request),final.ref(plan))):m.reject('最终结果未登记计划依赖。')
            final.validate_result(request,plan,data)
        elif kind=='final_score':
            request=resolve(rows,data['boundary_request_ref'],'boundary_request');plan=resolve(rows,data['boundary_plan_ref'],'boundary_plan')
            deps=[final.ref(request),final.ref(plan)]
            if data['kind']=='final':
                result=next((r['data'] for r in rows.values() if r['kind']=='boundary_result' and r['data']['plan_ref']==final.ref(plan) and r['data']['request_fingerprint']==final.request_fingerprint(request)),None)
                if result is None:m.reject('最终乐谱缺少边界结果事实。')
                deps.append(final.ref(result))
            if any(dep not in row['dependencies'] for dep in deps):m.reject('最终乐谱缺少原生阶段依赖。')
            final.validate_final_score(request,plan,data)
        elif kind=='audio_asset':
            if data['score_ref'] not in row['dependencies']:m.reject('音频未登记所选乐谱依赖。')
            audio.validate_asset(data,resolve(rows,data['score_ref'],'final_score'),files=False)
        elif kind=='application':
            m.shape(data,'transaction_id candidate_ref score_ref input_snapshot_id pre_revision post_revision accepted_binding_fingerprint registered_source_ids registered_material_ids accepted_record_id result_id')
            resolve(rows,data['score_ref'],'final_score')
            if data['score_ref'] not in row['dependencies']:m.reject('应用未登记乐谱依赖。')
        else:m.reject('未知最终事实类型。')
        if row!=fact(kind,data,row['dependencies']):m.reject('最终事实原生指纹或身份被篡改。')
        visiting.remove(ident);seen.add(ident)
    for ident in rows:visit(ident)
    return rows


def _cancel(check):
    if check and check():m.reject('已取消推荐计算。','CANCELLED')


def capabilities(candidate,ready=True,accepted=False):
    local=bool(candidate['remaining_gaps'])
    return dict(score_scope='LOCAL' if local else 'FULL',target_complete=True,can_preview=True,
        can_play_comparison=ready,can_play_final=ready,can_apply=ready,can_export_final=accepted and not local,
        blocking_reasons=[] if ready else ['音频尚未准备完成或文件已不可用。'])


def _failure(exc):
    return dict(code=getattr(exc,'code','RECOMMENDATION_FAILED'),message=str(exc) or '方案处理失败，编辑已保留，请查看详情后重试。',
        details=dict(exception_type=type(exc).__name__,exception=repr(exc),traceback=traceback.format_exc()))


def source_snapshots(project,source_facts):
    """Reconstruct only original input facts, without composing or stripping audit."""
    rows=validate_facts(source_facts);snapshots={};visiting=set();visited=set()
    def walk(value,depth=0):
        if depth>32:m.reject('原输入快照超过来源闭包深度预算。','SOURCE_CLOSURE_INVALID')
        for record in value['records']:
            if record['kind']!='accepted_candidate':continue
            payload=record['payload'];reference=payload.get('application_ref')
            if reference is None:m.reject('此旧接受记录缺少P7原输入证明；保留工程，请使用其历史输出。','SOURCE_CLOSURE_INVALID')
            receipt=resolve(rows,reference,'application');score=resolve(rows,payload['score_ref'],'final_score')
            req=resolve(rows,score['boundary_request_ref'],'boundary_request');original=req['connection_ref']['request']['input_project']
            ident=payload['input_snapshot_id'];fingerprint=m.fingerprint(original)
            if (receipt['score_ref']!=payload['score_ref'] or receipt['input_snapshot_id']!=ident or req['token']['snapshot_id']!=ident
                    or req['input_fingerprint']!=fingerprint or record['input_fingerprint']!=fingerprint or original['project_id']!=project['project_id']):
                m.reject('原输入快照、版本或Application来源不匹配。','SOURCE_CLOSURE_INVALID')
            snap=dict(id=ident,spec_rev=m.SPEC_REV,contract_rev=original['contract_rev'],content_fingerprint=fingerprint,project=copy.deepcopy(original))
            if ident in snapshots and snapshots[ident]!=snap:m.reject('同ID原快照被替换。','SOURCE_CLOSURE_INVALID')
            snapshots[ident]=snap
            if ident in visiting:m.reject('原输入接受引用形成循环。','SOURCE_CLOSURE_INVALID')
            if ident in visited:continue
            visiting.add(ident);walk(original,depth+1);visiting.remove(ident);visited.add(ident)
    walk(project)
    return [snapshots[k] for k in sorted(snapshots)]


def prepare_recommendations(request,source_facts=None,should_cancel=None,on_progress=None):
    with m.deterministic_ids(request_fingerprint(request)):
        return _prepare_recommendations(request,source_facts,should_cancel,on_progress)


def _prepare_recommendations(request,source_facts=None,should_cancel=None,on_progress=None):
    """Every recommendation goes through actual P4/P5/P6 before final processing."""
    validate_request(request)
    from curve_workflow import Controller,decide_bridge,generate_bridges
    import curve_store
    import curve_boundary_music
    import story_engine
    private=Controller(request['input_project'])
    if source_facts is not None or any(r['kind']=='accepted_candidate' for r in request['input_project']['records']):
        private._bundle['schema']='emoblocks.curve-bundle.v2';private._bundle['final_facts']=copy.deepcopy(source_facts)
        if source_facts is None:m.reject('缺少本次捕获的已接受来源闭包，请重新计算。','SOURCE_CLOSURE_INVALID')
        private._bundle['snapshots']=source_snapshots(request['input_project'],source_facts)
        curve_store.validate_bundle(private._bundle)
    seq=0;current=None;facts=[];candidates=[];failures=[];duplicates=0;tested=0
    def emit(phase,message):
        nonlocal seq
        seq+=1;event=dict(seq=seq,phase=phase,message=message,candidate_id=current,stage_bundle=private._current_bundle())
        if on_progress is not None:
            response=on_progress(event)
            if response is False or isinstance(response,dict) and not response.get('continue_processing',True):m.reject('输入已改变或请求已取消。','CANCELLED')
        _cancel(should_cancel)
    try:
        if request['target_gaps']:
            emit('BASE_COMPLETION','生成真实基础补全候选。')
            selected=request['target_gaps'][0]['id'] if request['scope']=='selected' else None
            captured=private.capture_completion(selected,request['seed'],request['parameters']['completion_budget'])
            outcome=completion.prepare_completion(captured['request'],should_cancel=should_cancel)
            private.finish_completion(captured['token'],outcome)
            bases=outcome['candidates'][:request['parameters']['max_pipeline_candidates']]
            if not bases:failures.append(outcome['error'])
        else:
            captured=None;bases=[None]
        for base in bases:
            _cancel(should_cancel);tested+=1;current=base['id'] if base else None
            try:
                emit('BRIDGE_DECISION','判断桥接是否有音乐收益。')
                job=private.capture_bridge(current,captured['attempt_id'] if captured else None,request['seed'],request['parameters']['bridge_parameters'])
                proposal=decide_bridge(job['request'],should_cancel=should_cancel)
                plan=private.lock_bridge(job['token'],proposal)
                emit('BRIDGE_LOCKED','桥接位置与全部保护已在同一事务登记。')
                private.begin_bridge_generation(job['token'],plan);emit('BRIDGE_GENERATION','生成并逐项验证桥接乐句。')
                def bridge_result(value):
                    private.record_bridge_result(job['token'],value);emit('BRIDGE_GENERATION','已登记桥接实际结果与保护。')
                raw=generate_bridges(job['request'],plan,should_cancel=should_cancel,on_result=bridge_result)
                private.finish_bridge(job['token'],raw)
                if private.bridge_state()['status']!='READY':m.reject('桥接未完整就绪。','BRIDGE_NOT_READY')
                emit('CONNECTIONS','在已就绪桥接保护之外规划连接块。')
                con=private.capture_connection(job['attempt_id'],request['seed'],request['parameters']['connection_parameters'])
                prop=story_engine.plan_connection_request(con['request'],should_cancel=should_cancel)
                cp=private.plan_connection(con['token'],prop);private.begin_connection_generation(con['token'],cp)
                def connection_result(value):
                    private.record_connection_result(con['token'],value);emit('CONNECTIONS','登记连接块实际音乐。')
                raw=story_engine.generate_connection_request(con['request'],cp,con['request']['actual_layout'],should_cancel=should_cancel,on_result=connection_result)
                private.finish_connection(con['token'],raw)
                attempt=private._connection_attempt(con['attempt_id']);cref=dict(attempt_id=attempt['id'],**{k:copy.deepcopy(attempt['connection'][k]) for k in ('request','plan','results','outcome')})
                emit('BOUNDARIES','统一规划最终局部交接。')
                req=final.make_request(cref,request['token'],seed=request['seed'],values=request['parameters']['boundary_parameters'])
                proposal=story_engine.plan_boundary_request(req,should_cancel=should_cancel)
                bp=final.make_plan(req,proposal);br=final.apply_boundaries(req,bp)
                emit('VALIDATION','独立复核实际音符、来源、时长与完整保护。')
                stages=dict(completion_attempt_id=captured['attempt_id'] if captured else None,completion_candidate_id=current,
                    bridge_attempt_id=job['attempt_id'],connection_attempt_id=con['attempt_id'],boundary_request_id=req['id'],boundary_plan_id=bp['id'],boundary_result_id=br['id'])
                request_ref=dict(id=request['token']['request_id'],version=1,fingerprint=request['request_fingerprint'])
                identity=m.digest('emoblocks.final-candidate.v1',dict(request_ref=request_ref,stage_refs=stages,BoundaryResultRef=final.ref(br)))
                candidate_ref=dict(id=identity,version=1,fingerprint=identity)
                emit('ARRANGEMENT','按已确定乐谱准备所选编配模式。')
                fs=final.make_score(req,bp,br,request['mode']);comparison=final.make_score(req,bp,br,request['mode'],'comparison')
                final.validate_final_score(req,bp,fs);final.validate_final_score(req,bp,comparison)
                if any(x['music_fingerprint']==fs['music_fingerprint'] for x in candidates):duplicates+=1;continue
                parents=[]
                for record in req['actual_layout']['base_project']['records']:
                    overlay=record['payload'].get('p7') if record['kind']=='final_score' else None
                    if overlay and overlay['score_ref'] not in parents:parents.append(overlay['score_ref'])
                cf=fact('boundary_request',req,parents);pf=fact('boundary_plan',bp,[final.ref(req)]);rf=fact('boundary_result',br,[final.ref(req),final.ref(bp)])
                ff=fact('final_score',fs,[final.ref(req),final.ref(bp),final.ref(br)]);sf=fact('final_score',comparison,[final.ref(req),final.ref(bp)])
                emit('RENDERING','真实 LMMS 连续渲染原基础与处理后对比。')
                pair=dict(comparison=audio.render(comparison,candidate_ref,should_cancel=should_cancel),final=audio.render(fs,candidate_ref,should_cancel=should_cancel))
                newfacts=[cf,pf,rf,ff,sf]+[fact('audio_asset',v,[v['score_ref']]) for v in pair.values()]
                facts.extend(newfacts)
                candidate=dict(id=identity,version=1,request_ref=request_ref,stage_refs=stages,final_score_ref=final.ref(fs),comparison_score_ref=final.ref(comparison),
                    music_fingerprint=fs['music_fingerprint'],remaining_gaps=copy.deepcopy(fs['remaining_gaps']),rank=len(candidates)+1,
                    reasons=[x['message'] if isinstance(x,dict) else str(x) for x in bp['reasons']],assets=pair,capabilities=None,modes={})
                candidate['capabilities']=capabilities(candidate)
                candidate['modes'][request['mode']]=dict(status='AUDITION_READY',final_score_ref=final.ref(fs),comparison_score_ref=final.ref(comparison),
                    assets=copy.deepcopy(pair),error=None,capabilities=copy.deepcopy(candidate['capabilities']))
                candidates.append(candidate)
                if len(candidates)>=request['parameters']['max_recommendations']:break
            except Exception as exc:
                if getattr(exc,'code',None)=='CANCELLED':raise
                failures.append(_failure(exc))
                # Failed locks remain in that private attempt; terminate active jobs.
                for tokenid,active in list(private._jobs.items()):
                    token=private.session._requests.get(tokenid)
                    if token and active['kind']=='BRIDGE':private.fail_bridge(token,_failure(exc))
                    elif token and active['kind']=='CONNECTION':private.fail_connection(token,_failure(exc))
        status='SUCCEEDED' if len(candidates)>=2 else 'INSUFFICIENT' if candidates else 'FAILED'
        error=None if candidates else (failures[0] if failures else dict(code='NO_VALID_RECOMMENDATION',message='未得到合法完整方案。',details={}))
    except Exception as exc:
        status='CANCELLED' if getattr(exc,'code',None)=='CANCELLED' else 'FAILED';error=_failure(exc)
    stage=private._current_bundle()
    # Never store running threads. Preserve their facts and locks as interrupted audit.
    if status in ('CANCELLED','FAILED'):
        for attempt in stage['attempts']:
            if attempt['state']=='RUNNING':attempt['state']='INTERRUPTED'
    value=dict(final.header('emoblocks.recommendation-outcome.v1'),request_fingerprint=request['request_fingerprint'],status=status,
        candidates=candidates,facts=facts,stage_bundle=stage,
        search=dict(tested_candidates=tested,completed_candidates=len(candidates),duplicate_candidates=duplicates,termination='CANCELLED' if status=='CANCELLED' else 'COMPLETE'),
        insufficient_reason=None if len(candidates)>=2 else '完整流水线仅得到 '+str(len(candidates))+' 套实际不同的有效方案。',failures=failures,error=error)
    value['outcome_fingerprint']=outcome_fingerprint(value);validate_outcome(request,value);return value


@m.validated_operation
@final.guard
def validate_outcome(request,value):
    validate_request(request);m.shape(value,OUTCOME_FIELDS);final.version(value,'emoblocks.recommendation-outcome.v1')
    if value['request_fingerprint']!=request['request_fingerprint'] or value['outcome_fingerprint']!=outcome_fingerprint(value):m.reject('完整推荐身份或内容指纹不一致。','STALE_SNAPSHOT')
    import curve_store
    curve_store.validate_bundle(value['stage_bundle'])
    if value['stage_bundle']['project']!=request['input_project']:m.reject('候选计算修改了输入工程。','SNAPSHOT_ISOLATION')
    combined=list(value['stage_bundle'].get('final_facts',[]))+value['facts']
    rows=validate_facts(combined,value['stage_bundle'],{r['id'] for r in value['facts']});seen=set()
    for candidate in value['candidates']:
        m.shape(candidate,'id version request_ref stage_refs final_score_ref comparison_score_ref music_fingerprint remaining_gaps rank reasons assets capabilities modes')
        stages=candidate['stage_refs']
        m.shape(stages,'completion_attempt_id completion_candidate_id bridge_attempt_id connection_attempt_id boundary_request_id boundary_plan_id boundary_result_id')
        req=rows[stages['boundary_request_id']]['data'];plan=rows[stages['boundary_plan_id']]['data'];result=rows[stages['boundary_result_id']]['data']
        con=req['connection_ref'];br=con['request']['bridge_ref'];parent=br['request']['completion_ref']
        if (rows[stages['boundary_request_id']]['kind']!='boundary_request' or rows[stages['boundary_plan_id']]['kind']!='boundary_plan' or rows[stages['boundary_result_id']]['kind']!='boundary_result'
                or req['token']!=request['token'] or req['input_fingerprint']!=request['input_fingerprint'] or con['request']['input_project']!=request['input_project']
                or stages['connection_attempt_id']!=con['attempt_id'] or stages['bridge_attempt_id']!=br['attempt_id']
                or stages['completion_attempt_id']!=(parent['attempt_id'] if parent else None) or stages['completion_candidate_id']!=(parent['candidate_id'] if parent else None)
                or result['plan_ref']!=final.ref(plan) or result['request_fingerprint']!=final.request_fingerprint(req)):
            m.reject('推荐阶段引用与实际完整流水线不一致。','PLAN_VERSION_MISMATCH')
        identity=m.digest('emoblocks.final-candidate.v1',dict(request_ref=candidate['request_ref'],stage_refs=stages,BoundaryResultRef=final.ref(result)))
        if candidate['id']!=identity or candidate['version']!=1 or candidate['request_ref']!=dict(id=request['token']['request_id'],version=1,fingerprint=request['request_fingerprint']):m.reject('最终推荐不是当前请求的候选。')
        score=resolve(rows,candidate['final_score_ref'],'final_score');comparison=resolve(rows,candidate['comparison_score_ref'],'final_score')
        if any(s['boundary_request_ref']!=final.ref(req) or s['boundary_plan_ref']!=final.ref(plan) for s in (score,comparison)) or score['kind']!='final' or comparison['kind']!='comparison' or score['mode']!=request['mode'] or comparison['mode']!=request['mode']:
            m.reject('候选对比乐谱没有绑定同一阶段与模式。','OUTPUT_BINDING_MISMATCH')
        if score['music_fingerprint'] in seen:m.reject('最终音乐相同的结果不能算两套推荐。')
        seen.add(score['music_fingerprint'])
        if candidate['music_fingerprint']!=score['music_fingerprint'] or candidate['remaining_gaps']!=score['remaining_gaps']:m.reject('推荐范围或音乐指纹不符。')
        for kind in ('final','comparison'):audio.validate_asset(candidate['assets'][kind],score if kind=='final' else comparison,dict(id=identity,version=1,fingerprint=identity),files=False)
        if candidate['assets']['final']['version']!=candidate['assets']['comparison']['version']:m.reject('对比资产版本不能混用。')
        if candidate['capabilities']!=capabilities(candidate):m.reject('候选资格与实际剩余空缺不符。')
        for mode,member in candidate['modes'].items():
            m.shape(member,'status final_score_ref comparison_score_ref assets error capabilities')
            if mode not in ('melody_only','arranged') or member['status']!='AUDITION_READY' or member['capabilities']!=capabilities(candidate):m.reject('候选模式资格不符。')
            for kind in ('final','comparison'):
                s=resolve(rows,member[kind+'_score_ref'],'final_score')
                if s['kind']!=kind or s['mode']!=mode or s['boundary_request_ref']!=final.ref(req) or s['boundary_plan_ref']!=final.ref(plan):m.reject('候选模式绑定另一份乐谱。')
                audio.validate_asset(member['assets'][kind],s,dict(id=identity,version=1,fingerprint=identity),files=False)
            if member['assets']['final']['version']!=member['assets']['comparison']['version']:m.reject('候选模式资产版本不一致。')
    expected='SUCCEEDED' if len(seen)>=2 else 'INSUFFICIENT' if seen else value['status']
    if value['status']!=expected or expected not in ('SUCCEEDED','INSUFFICIENT','FAILED','CANCELLED'):m.reject('推荐状态与真实数量不符。')


def prepare_candidate_mode(request,candidate_id,mode,source_facts,should_cancel=None,on_progress=None):
    """Only compile/render the already saved boundary result, never rerun music."""
    rows=validate_facts(source_facts)
    score=next((r['data'] for r in rows.values() if r['kind']=='final_score' and r['data']['kind']=='final' and any(
        a['kind']=='audio_asset' and a['data']['candidate_ref']['id']==candidate_id and a['data']['score_ref']['id']==r['id'] for a in rows.values())),None)
    if score is None:m.reject('没有已准备好的候选乐谱。')
    req=resolve(rows,score['boundary_request_ref']);plan=resolve(rows,score['boundary_plan_ref']);result=final.apply_boundaries(req,plan)
    fs=final.make_score(req,plan,result,mode);comparison=final.make_score(req,plan,result,mode,'comparison')
    reference=dict(id=candidate_id,version=1,fingerprint=candidate_id)
    version=1+max([r['data']['version'] for r in rows.values() if r['kind']=='audio_asset' and r['data']['candidate_ref']['id']==candidate_id] or [0])
    pair=dict(comparison=audio.render(comparison,reference,version,should_cancel),final=audio.render(fs,reference,version,should_cancel))
    return dict(candidate_id=candidate_id,mode=mode,final_score=fs,comparison_score=comparison,assets=pair,error=None)


@m.validated_operation
def validate_p7_bundle(bundle):
    import curve_store
    m.canonical(bundle);m.shape(bundle,'schema spec_rev contract_rev project snapshots attempts results final_facts')
    plain=copy.deepcopy(bundle);plain['schema']=curve_store.SCHEMA;plain.pop('final_facts')
    plain['attempts']=[a for a in plain['attempts'] if 'recommendation' not in a]
    curve_store._validate_bundle(plain)
    rows=validate_facts(bundle['final_facts'])
    snapshots=m.indexed(bundle['snapshots'])
    for attempt in bundle['attempts']:
        if 'recommendation' not in attempt:continue
        m.shape(attempt,'id snapshot_id input_fingerprint state records protections staged_materials error recommendation')
        value=attempt['recommendation'];m.shape(value,'schema spec_rev contract_rev request phase last_seq cancel_requested partial_stage_bundle outcome mode_bindings mode_jobs receipt')
        final.version(value,'emoblocks.recommendation-attempt.v1');request=value['request'];validate_request(request)
        snap=snapshots.get(attempt['snapshot_id'])
        if snap is None or snap['project']!=request['input_project'] or attempt['id']!=request['token']['request_id'] or attempt['input_fingerprint']!=request['input_fingerprint'] or any(attempt[k] for k in ('records','protections','staged_materials')):m.reject('推荐暂存与原输入快照不一致。')
        if attempt['state'] not in ('RUNNING','READY','FAILED','CANCELLED','INTERRUPTED','STALE','APPLIED'):m.reject('推荐暂存状态无效。')
        if value['partial_stage_bundle'] is not None:
            curve_store.validate_bundle(value['partial_stage_bundle'])
            if value['partial_stage_bundle']['project']!=request['input_project']:m.reject('阶段审计修改了原输入。')
        if value['outcome'] is not None:
            validate_outcome(request,value['outcome'])
            for row in value['outcome']['facts']:
                if rows.get(row['id'])!=row:m.reject('最终结果未登记真实事实闭包。')
            expected_bindings={candidate['id']:{mode:dict(final_score_ref=member['final_score_ref'],comparison_score_ref=member['comparison_score_ref'],
                comparison_asset_ref=final.ref(member['assets']['comparison']),final_asset_ref=final.ref(member['assets']['final']),asset_version=member['assets']['final']['version'])
                for mode,member in candidate['modes'].items()} for candidate in value['outcome']['candidates']}
            if value['mode_bindings']!=expected_bindings:m.reject('保存的试听模式绑定与实际资产不符。','OUTPUT_BINDING_MISMATCH')
        if attempt['state'] in ('RUNNING','READY') and attempt['input_fingerprint']!=m.fingerprint(bundle['project']):m.reject('输入变化后旧推荐未失效。','STALE_SNAPSHOT')
        if value['receipt'] is not None:
            if resolve(rows,dict(id=value['receipt']['transaction_id'],version=1,fingerprint=m.digest('emoblocks.application.v1',value['receipt'])),'application')!=value['receipt']:m.reject('应用审计缺失。')
    for project in [bundle['project']]+[s['project'] for s in bundle['snapshots']]:
        for record in project['records']:
            overlay=record['payload'].get('p7') if record['kind']=='final_score' else None
            if overlay:
                score=resolve(rows,overlay['score_ref'],'final_score')
                if score!=overlay['final_score'] or record['payload']['notes']!=score['notes'] or record['payload']['total_ticks']!=score['total_ticks'] or overlay['mode']!=score['mode'] or record['payload']['protection_summary_fingerprint']!=score['protection_summary_fingerprint']:
                    m.reject('工程覆盖引用了不同乐谱。')
                accepted=next((r for r in project['records'] if r['kind']=='accepted_candidate' and r['payload']['final_score_id']==record['id']),None)
                if accepted is None:m.reject('工程覆盖缺少接受事务。')
                receipt=resolve(rows,accepted['payload']['application_ref'],'application')
                if (receipt['score_ref']!=overlay['score_ref'] or receipt['candidate_ref']!=overlay['candidate_ref'] or receipt['accepted_binding_fingerprint']!=overlay['binding_fingerprint']
                        or receipt['accepted_record_id']!=accepted['id'] or receipt['result_id']!=accepted['payload']['result_id'] or receipt['input_snapshot_id']!=accepted['payload']['input_snapshot_id']
                        or accepted['payload']['score_ref']!=overlay['score_ref'] or accepted['payload']['mode']!=overlay['mode']):m.reject('接受事务、工程覆盖与来源不一致。')


class RecommendationFacade:
    """All publication/application methods are called by the desktop main thread."""
    def _recommendation_attempt(self,ident=None):
        ident=ident or getattr(self,'_recommendation_id',None)
        return next((a for a in self._bundle['attempts'] if a['id']==ident and 'recommendation' in a),None)

    def capture_recommendations(self,selected_gap_id=None,seed=31,parameters=None,mode=None):
        self._editable()
        if self._jobs:m.reject('已有任务正在准备，请等待或取消。','DUPLICATE_REQUEST')
        captured=self.session.capture(contract_rev=REV);token=captured['token']
        try:
            request=make_request(captured['project'],token,selected_gap_id,seed,parameters,mode)
            bundle=self._current_bundle();bundle['schema']='emoblocks.curve-bundle.v2';bundle.setdefault('final_facts',[])
            bundle['snapshots'].append(dict(id=token['snapshot_id'],spec_rev=m.SPEC_REV,contract_rev=request['input_contract_rev'],content_fingerprint=request['input_fingerprint'],project=copy.deepcopy(request['input_project'])))
            value=dict(final.header('emoblocks.recommendation-attempt.v1'),request=request,phase=None,last_seq=0,cancel_requested=False,partial_stage_bundle=None,outcome=None,mode_bindings={},mode_jobs=[],receipt=None)
            bundle['attempts'].append(dict(id=token['request_id'],snapshot_id=token['snapshot_id'],input_fingerprint=token['input_fingerprint'],state='RUNNING',records=[],protections=[],staged_materials=[],error=None,recommendation=value))
            validate_p7_bundle(bundle)
        except Exception:self.session.finish(token);raise
        self._bundle=bundle;self._jobs[token['request_id']]=dict(kind='RECOMMENDATION',request=copy.deepcopy(request));self._recommendation_id=token['request_id'];self._staging_dirty=True
        return dict(token=copy.deepcopy(token),request=copy.deepcopy(request),attempt_id=token['request_id'],source_facts=copy.deepcopy(bundle['final_facts']))

    def record_recommendation_progress(self,token,event):
        attempt=self._recommendation_attempt(token.get('request_id'));reply=dict(accepted=False,continue_processing=False)
        if attempt is None or attempt['recommendation']['request']['token']!=token:return reply
        m.shape(event,'seq phase message candidate_id stage_bundle');value=attempt['recommendation'];m.integer(event['seq'],1)
        if event['seq']<=value['last_seq']:return reply
        import curve_store
        stage=event['stage_bundle'];curve_store.validate_bundle(stage)
        if stage['project']!=value['request']['input_project']:m.reject('候选阶段快照不一致。')
        old=value['partial_stage_bundle']
        if old:
            old_attempts=m.indexed(old['attempts']);new_attempts=m.indexed(stage['attempts'])
            for ident,row in old_attempts.items():
                if ident not in new_attempts:m.reject('新进度删除了既有阶段审计。')
                if 'bridge' in row:
                    newer=new_attempts[ident]
                    if row['bridge']['plan'] is not None and row['bridge']['plan']!=newer['bridge']['plan']:m.reject('进度改变了已锁定桥计划。')
                    lock_ids={p['id'] for p in newer['protections']}
                    if not {p['id'] for p in row['protections']}<=lock_ids:m.reject('进度释放了桥保护。')
                    for lock in row['protections']:
                        current=next(p for p in newer['protections'] if p['id']==lock['id'])
                        if lock['status']=='CONTENT_READY' and current!=lock:m.reject('进度覆盖了已有就绪桥内容。')
                    for result in row['bridge']['results']:
                        if result not in newer['bridge']['results']:m.reject('进度撤销或覆盖了实际桥结果。')
        active=self.accepts(token) and attempt['state']=='RUNNING' and not value['cancel_requested']
        value['last_seq']=event['seq'];value['partial_stage_bundle']=copy.deepcopy(stage)
        if attempt['state']=='RUNNING':value['phase']=event['phase']
        self._staging_dirty=True
        return dict(accepted=True,continue_processing=active)

    @m.validated_operation
    def finish_recommendations(self,token,outcome):
        attempt=self._recommendation_attempt(token.get('request_id'))
        if attempt is None or not self.accepts(token) or attempt['state']!='RUNNING':return False
        value=attempt['recommendation'];validate_outcome(value['request'],outcome)
        if value['cancel_requested'] and outcome['status']!='CANCELLED':return False
        for candidate in outcome['candidates']:
            for mode,member in candidate['modes'].items():
                for kind,asset in member['assets'].items():audio.validate_asset(asset,resolve(outcome['facts'],member[kind+'_score_ref']),dict(id=candidate['id'],version=1,fingerprint=candidate['id']))
        bundle=self._current_bundle();target=next(a for a in bundle['attempts'] if a['id']==attempt['id']);v=target['recommendation']
        target['state']='READY' if outcome['status'] in ('SUCCEEDED','INSUFFICIENT') else outcome['status'];target['error']=copy.deepcopy(outcome['error'])
        v['outcome']=copy.deepcopy(outcome);v['partial_stage_bundle']=copy.deepcopy(outcome['stage_bundle']);v['phase']='AUDITION_READY' if target['state']=='READY' else v['phase']
        for candidate in outcome['candidates']:
            v['mode_bindings'][candidate['id']]={mode:dict(final_score_ref=member['final_score_ref'],comparison_score_ref=member['comparison_score_ref'],
                comparison_asset_ref=final.ref(member['assets']['comparison']),final_asset_ref=final.ref(member['assets']['final']),asset_version=member['assets']['final']['version']) for mode,member in candidate['modes'].items()}
        rows=m.indexed(bundle['final_facts'])
        for row in outcome['facts']:
            if row['id'] in rows and rows[row['id']]!=row:m.reject('新推荐覆盖了既有乐谱事实。')
            if row['id'] not in rows:bundle['final_facts'].append(copy.deepcopy(row))
        validate_p7_bundle(bundle)
        if not self.session.finish(token):return False
        self._jobs.pop(token['request_id'],None);self._bundle=bundle;self._staging_dirty=True;return True

    def cancel_recommendations(self,token):
        attempt=self._recommendation_attempt(token.get('request_id'))
        if attempt is None or not self.accepts(token):return False
        attempt['recommendation']['cancel_requested']=True;attempt['recommendation']['phase']='CANCEL_REQUESTED';self._staging_dirty=True;return True

    def fail_recommendations(self,token,error,stage_bundle=None):
        attempt=self._recommendation_attempt(token.get('request_id'))
        if attempt is None or not self.accepts(token):return False
        if stage_bundle is not None:
            self.record_recommendation_progress(token,dict(seq=attempt['recommendation']['last_seq']+1,phase='VALIDATION',message='保存失败阶段审计。',candidate_id=None,stage_bundle=stage_bundle))
        attempt['state']='CANCELLED' if attempt['recommendation']['cancel_requested'] else 'FAILED';attempt['error']=copy.deepcopy(error)
        self.session.finish(token);self._jobs.pop(token['request_id'],None);self._staging_dirty=True;return True

    def _candidate(self,candidate_id):
        for attempt in reversed(self._bundle['attempts']):
            if 'recommendation' not in attempt or attempt['recommendation']['outcome'] is None:continue
            for candidate in attempt['recommendation']['outcome']['candidates']:
                if candidate['id']==candidate_id:return attempt,candidate
        m.reject('所选方案不存在，请重新计算。','STALE_SNAPSHOT')

    def _apply_authorized(self,attempt):
        request=attempt['recommendation']['request'];token=request['token']
        live=token['session_id']==self.session._session_id and token['edit_revision']==self.session._revision
        restored=self._loaded is not None and self.session._revision==0
        return attempt['state']=='READY' and (live or restored) and request['input_fingerprint']==m.fingerprint(self.project)

    def recommendation_asset(self,candidate_id,kind='final',mode=None):
        attempt,candidate=self._candidate(candidate_id);mode=mode or attempt['recommendation']['request']['mode']
        if kind not in ('final','comparison') or mode not in candidate['modes']:m.reject('试听模式尚未准备。','OUTPUT_FILE_UNAVAILABLE')
        member=candidate['modes'][mode];asset=member['assets'][kind];score=resolve(self._bundle['final_facts'],member[kind+'_score_ref'],'final_score')
        audio.validate_asset(asset,score,dict(id=candidate_id,version=1,fingerprint=candidate_id),required_formats=('wav',));return copy.deepcopy(asset)

    def confirmation_ref(self,candidate_id,mode=None):
        attempt,candidate=self._candidate(candidate_id)
        if not self._apply_authorized(attempt):m.reject('编辑或会话已改变，请重新计算。','STALE_SNAPSHOT')
        mode=mode or attempt['recommendation']['request']['mode'];member=candidate['modes'][mode]
        pair={kind:self.recommendation_asset(candidate_id,kind,mode) for kind in ('comparison','final')}
        return dict(session_id=self.session._session_id,edit_revision=self.session._revision,input_fingerprint=m.fingerprint(self.project),
            candidate_ref=dict(id=candidate_id,version=1,fingerprint=candidate_id),mode=mode,final_score_ref=copy.deepcopy(member['final_score_ref']),
            comparison_score_ref=copy.deepcopy(member['comparison_score_ref']),asset_pair_fingerprint=m.digest('emoblocks.asset-pair.v1',{k:final.ref(v) for k,v in pair.items()}))

    @m.validated_operation
    def apply_recommendation(self,candidate_id,transaction_id=None,mode=None,confirmation_ref=None):
        from curve_application import prepare_application,accepted_state
        attempt,candidate=self._candidate(candidate_id);value=attempt['recommendation'];mode=mode or value['request']['mode'];transaction_id=transaction_id or 'apply:'+candidate_id
        receipt=value['receipt']
        if receipt is not None:
            if transaction_id!=receipt['transaction_id'] or candidate['modes'][mode]['final_score_ref']!=receipt['score_ref']:m.reject('同一确认事务不能改为另一乐谱。','DUPLICATE_TRANSACTION')
            if accepted_state(self.project)['status']!='ACTIVE' or self.project['accepted_candidate_id']!=receipt['accepted_record_id']:m.reject('已撤销的确认不能复活旧事务；请重做或重新计算。','STALE_SNAPSHOT')
            return dict(changed=False,receipt=copy.deepcopy(receipt))
        ref_=self.confirmation_ref(candidate_id,mode)
        if confirmation_ref is not None and confirmation_ref!=ref_:m.reject('试听与确认的版本已变化。','STALE_SNAPSHOT')
        request=value['request'];validate_outcome(request,value['outcome'])
        future,receipt,application=prepare_application(self.project,candidate,self._bundle['final_facts'],attempt['snapshot_id'],transaction_id,self.session._revision,mode)
        bundle=self._current_bundle();bundle['project']=future;bundle['contract_rev']=future['contract_rev'];bundle['final_facts'].append(application)
        target=next(a for a in bundle['attempts'] if a['id']==attempt['id']);target['state']='APPLIED';target['recommendation']['receipt']=receipt
        for other in bundle['attempts']:
            if other is not target and other['state'] in ('RUNNING','READY'):other['state']='STALE'
        bundle['results'].append(dict(id=receipt['result_id'],candidate_id=candidate_id,mode=mode,score_ref=receipt['score_ref'],
            generated_at=datetime.now(timezone.utc).isoformat(),scope='LOCAL' if candidate['remaining_gaps'] else 'FULL'))
        validate_p7_bundle(bundle)
        self.save_snapshot() # durable staging protection is the last fallible step
        self.session.apply_prepared(future,ref_['edit_revision'],ref_['input_fingerprint'])
        self._bundle=bundle;self._jobs.clear();self._staging_dirty=True;self._untouched_new=False
        return dict(changed=True,receipt=copy.deepcopy(receipt))

    def recommendation_state(self):
        from curve_application import accepted_state
        attempt=self._recommendation_attempt();status=attempt['state'] if attempt else 'IDLE';value=attempt['recommendation'] if attempt else None
        out=value['outcome'] if value else None;dtos=[]
        if out:
            facts=self._bundle['final_facts']
            for candidate in out['candidates']:
                score=resolve(facts,candidate['final_score_ref']);req=resolve(facts,score['boundary_request_ref']);plan=resolve(facts,score['boundary_plan_ref'])
                modes=copy.deepcopy(candidate['modes'])
                for mode,member in modes.items():
                    playable={}
                    for kind in ('comparison','final'):
                        try:self.recommendation_asset(candidate['id'],kind,mode);playable[kind]=True
                        except (OSError,ValueError,KeyError):playable[kind]=False
                    member['capabilities']=capabilities(candidate,all(playable.values()))
                    member['capabilities'].update(can_play_comparison=playable['comparison'],can_play_final=playable['final'],can_apply=all(playable.values()) and self._apply_authorized(attempt))
                    if not all(playable.values()):member['status']='MISSING'
                member=modes[value['request']['mode']]
                bridge=req['connection_ref']['request']['bridge_ref']
                view=connection.preview(req['connection_ref']['request'],req['connection_ref']['plan'],req['connection_ref']['results'],req['connection_ref']['outcome'])
                preview=dict(project=copy.deepcopy(req['actual_layout']['base_project']),notes=copy.deepcopy(score['notes']),protections=copy.deepcopy(req['actual_layout']['protections']),
                    bridge_overlays=copy.deepcopy(view['overlays']),
                    connection_overlays=copy.deepcopy(view['connection_overlays']),
                    boundary_overlays=[dict(id=b['id'],tick=b['tick'],method=b['method'],editable_ranges=b['editable_ranges'],operation_ids=b['operation_ids'],
                        performance_hint_ids=[h['id'] for h in plan['performance_hints'] if h['boundary_id']==b['id']],reasons=b['reasons']) for b in plan['boundaries']],
                    memory_info=__import__('curve_memory').memory_info(req['actual_layout']['base_project']))
                dtos.append(dict(id=candidate['id'],version=1,title='方案 '+str(candidate['rank']),scope=member['capabilities']['score_scope'],remaining_gaps=copy.deepcopy(candidate['remaining_gaps']),
                    rank=candidate['rank'],reasons=candidate['reasons'],score_ref=candidate['final_score_ref'],music_fingerprint=candidate['music_fingerprint'],assets=member['assets'],
                    capabilities=member['capabilities'],preview=preview,modes=modes))
        accepted=accepted_state(self.project) if not self.readonly else dict(candidate_ref=None)
        return dict(status=status,phase=value['phase'] if value else None,attempt_id=attempt['id'] if attempt else None,candidates=dtos,
            error=copy.deepcopy(attempt['error']) if attempt else None,message='方案已准备，可明确试听或确认。' if status=='READY' else '完整建议：'+status,
            search=copy.deepcopy(out['search']) if out else None,insufficient_reason=out['insufficient_reason'] if out else None,accepted_ref=accepted['candidate_ref'],
            capabilities=dict(can_calculate=not self.readonly and not self._jobs,can_cancel=status=='RUNNING',can_auto_complete=not self.readonly and not self._jobs))

    def effective_music(self):
        from curve_application import effective_music
        return effective_music(self.project,self._bundle.get('final_facts'))

    def accepted_state(self):
        from curve_application import accepted_state
        return accepted_state(self.project)

    def history(self):return self.history_items()

    def capture_recommendation_mode(self,candidate_id,mode):
        self._editable();attempt,candidate=self._candidate(candidate_id)
        if mode not in ('melody_only','arranged'):m.reject('输出模式不受支持。')
        if self._jobs:m.reject('已有任务正在准备，请等待或取消。','DUPLICATE_REQUEST')
        token=self.session.capture(contract_rev=REV)['token']
        job=dict(token=copy.deepcopy(token),candidate_id=candidate_id,mode=mode,asset_version=1+max([a['version'] for member in candidate['modes'].values() for a in member['assets'].values() if a] or [0]),status='RUNNING',error=None)
        attempt['recommendation']['mode_jobs'].append(job)
        self._jobs[token['request_id']]=dict(kind='RECOMMENDATION_MODE',candidate_id=candidate_id,mode=mode,attempt_id=attempt['id'])
        self._staging_dirty=True
        return dict(token=token,request=copy.deepcopy(attempt['recommendation']['request']),candidate_id=candidate_id,mode=mode,source_facts=copy.deepcopy(self._bundle['final_facts']))

    def finish_recommendation_mode(self,token,outcome):
        if not self.accepts(token):return False
        context=self._jobs[token['request_id']]
        if context['kind']!='RECOMMENDATION_MODE' or outcome['candidate_id']!=context['candidate_id'] or outcome['mode']!=context['mode']:m.reject('模式结果与请求不匹配。')
        bundle=self._current_bundle();attempt=next(a for a in bundle['attempts'] if a['id']==context['attempt_id']);value=attempt['recommendation']
        candidate=next(c for c in value['outcome']['candidates'] if c['id']==context['candidate_id']);job=next(j for j in value['mode_jobs'] if j['token']==token)
        m.shape(outcome,'candidate_id mode final_score comparison_score assets error')
        old=resolve(bundle['final_facts'],candidate['final_score_ref']);rows=index_facts(bundle['final_facts']);request=resolve(rows,old['boundary_request_ref']);plan=resolve(rows,old['boundary_plan_ref'])
        newfacts=[];candidate_ref=dict(id=candidate['id'],version=1,fingerprint=candidate['id'])
        for kind in ('final','comparison'):
            score=outcome[kind+'_score'];final.validate_final_score(request,plan,score)
            if score['mode']!=context['mode'] or score['kind']!=kind:m.reject('模式乐谱类型不一致。')
            asset=outcome['assets'][kind];audio.validate_asset(asset,score,candidate_ref)
            if asset['version']!=job['asset_version']:m.reject('模式音频版本不一致。')
            dependencies=[score['boundary_request_ref'],score['boundary_plan_ref']]
            if kind=='final':dependencies.append(final.ref(final.apply_boundaries(request,plan)))
            newfacts.extend([fact('final_score',score,dependencies),fact('audio_asset',asset,[final.ref(score)])])
        for row in newfacts:
            previous=rows.get(row['id'])
            if previous and previous['data']!=row['data']:m.reject('模式结果试图覆盖旧谱。')
            if previous:row=copy.deepcopy(previous)
            else:bundle['final_facts'].append(row);rows[row['id']]=row
            if not any(x['id']==row['id'] for x in value['outcome']['facts']):value['outcome']['facts'].append(row)
        member=dict(status='AUDITION_READY',final_score_ref=final.ref(outcome['final_score']),comparison_score_ref=final.ref(outcome['comparison_score']),assets=copy.deepcopy(outcome['assets']),error=None,capabilities=capabilities(candidate))
        candidate['modes'][context['mode']]=member
        value['mode_bindings'][candidate['id']][context['mode']]=dict(final_score_ref=member['final_score_ref'],comparison_score_ref=member['comparison_score_ref'],comparison_asset_ref=final.ref(member['assets']['comparison']),final_asset_ref=final.ref(member['assets']['final']),asset_version=job['asset_version'])
        value['outcome']['outcome_fingerprint']=outcome_fingerprint(value['outcome']);job['status']='READY'
        validate_p7_bundle(bundle)
        if not self.session.finish(token):return False
        self._bundle=bundle;self._jobs.pop(token['request_id'],None);self._staging_dirty=True;return True

    def _mode_terminal(self,token,error,status):
        if not self.accepts(token):return False
        context=self._jobs[token['request_id']]
        if context['kind']!='RECOMMENDATION_MODE':return False
        attempt=self._recommendation_attempt(context['attempt_id']);job=next(j for j in attempt['recommendation']['mode_jobs'] if j['token']==token)
        job['status']=status;job['error']=copy.deepcopy(error);self.session.finish(token);self._jobs.pop(token['request_id'],None);self._staging_dirty=True;return True

    def fail_recommendation_mode(self,token,error):return self._mode_terminal(token,error,'FAILED')

    def cancel_recommendation_mode(self,token):return self._mode_terminal(token,dict(code='CANCELLED',message='模式试听准备已取消。',details={}),'CANCELLED')

    def history_asset(self,result_id,mode=None):
        row=next((r for r in self._bundle['results'] if r.get('id')==result_id),None)
        if row and 'candidate_id' in row:return self.recommendation_asset(row['candidate_id'],'final',mode or row['mode'])
        item=next((r for r in self.history_items() if r['id']==result_id),None)
        if item is None or not item['availability']['wav']:m.reject('此历史音频已不可用。','SOURCE_UNAVAILABLE')
        return dict(wav_path=item['paths']['wav'],body_seconds=item['body_seconds'],audio_seconds=item['audio_seconds'],fingerprint=result_id)
