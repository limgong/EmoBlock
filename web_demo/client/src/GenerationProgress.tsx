import {Fragment,useEffect,useRef,useState} from 'react';
export type ProgressState={step:number;phase?:string;status:'queued'|'running'|'done'|'failed'|'cancelled'};

// Coarse milestones reached by the real job, not an estimated percentage or timer.
export function progressStep(phase?:string){
 const steps:Record<string,number>={BASE_COMPLETION:1,BRIDGE_DECISION:2,BRIDGE_LOCKED:2,BRIDGE_GENERATION:2,CONNECTIONS:3,BOUNDARIES:4,VALIDATION:5,ARRANGEMENT:6,RENDERING:7};
 return steps[phase||'']||0;
}

export function GenerationProgress({value,onCancel,disabled}:{value:ProgressState;onCancel?:()=>void;disabled:boolean}){
 const labels={queued:'方案已排队',running:'正在生成方案…',done:'方案已生成',failed:'生成未完成',cancelled:'已取消生成'};
 const operations:Record<string,string>={BASE_COMPLETION:'补齐旋律积木',BRIDGE_DECISION:'规划桥接位置',BRIDGE_LOCKED:'保护桥接位置',BRIDGE_GENERATION:'生成桥接旋律',CONNECTIONS:'衔接旋律积木',BOUNDARIES:'优化旋律边界',VALIDATION:'检查音乐结构',ARRANGEMENT:'编配音乐',RENDERING:'合成试听音频'};
 const operation=value.status==='running'?(operations[value.phase||'']||'准备音乐方案'):{queued:'等待生成',done:'音乐方案已完成',failed:'音乐方案生成中断',cancelled:'音乐方案已取消'}[value.status];
 const previous=useRef(operation);
 const [display,setDisplay]=useState({text:operation,complete:value.status==='done'});
 useEffect(()=>{
  const before=previous.current;previous.current=operation;
  if(value.status==='running'&&before!==operation){
   // Only acknowledge a stage after the backend has actually advanced.
   setDisplay({text:before,complete:true});
   const id=setTimeout(()=>setDisplay({text:operation,complete:false}),650);
   return()=>clearTimeout(id);
  }
  setDisplay({text:operation,complete:value.status==='done'});
 },[operation,value.status]);
 const current=value.status==='done'?8:value.step;
 return <section className={'generation-progress '+value.status} aria-label="方案生成状态">
  <div className="progress-heading"><strong role="status" aria-live="polite">{labels[value.status]}</strong>
   {onCancel&&<button disabled={disabled} onClick={onCancel}>取消生成</button>}
   {value.status==='done'&&<span className="muted">选择方案试听</span>}
  </div>
  <div className="progress-operation" role="status" aria-live="polite" aria-atomic="true">
   <span>{display.text}</span>
   {display.complete?<span aria-label="已完成">✅</span>:['queued','running'].includes(value.status)&&<><span className="operation-spinner" aria-hidden="true"/><span className="sr-only">处理中</span></>}
  </div>
  <div className="progress-scroll" tabIndex={0} aria-label="生成进度，窄窗口可横向滚动"><div className="progress-track" role="progressbar" aria-label="方案生成流程进度" aria-valuemin={0} aria-valuemax={8} aria-valuenow={current} aria-valuetext={display.text+' · '+labels[value.status]}>
   {Array.from({length:8},(_,i)=><Fragment key={i}>
    {i>0&&<span aria-hidden="true" className={'progress-link '+(i<=current?'reached':'')}/>}
    <span aria-hidden="true" className="progress-node" data-state={i<current?'complete':i===current?'current':'pending'}>{i<current?'✓':''}</span>
   </Fragment>)}
  </div></div>
 </section>
}
