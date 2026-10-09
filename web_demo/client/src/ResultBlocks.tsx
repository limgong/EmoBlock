import type {ReactNode} from 'react';
export type ResultSegment={id:string;start_tick:number;end_tick:number;role:string;role_label:string;display_name:string;emotion:string;notes:{pitch:number;start_tick:number;duration_tick:number;velocity:number}[];memory:boolean;partial:boolean};

export function ResultBlocks({segments,xAt,yAt,emotions,melody,onInspect}:{segments:ResultSegment[];xAt:(t:number)=>number;yAt:(t:number)=>number;emotions:Record<string,[string,string]>;melody:(s:ResultSegment,width:number)=>ReactNode;onInspect:(detail:string)=>void}){
 return <>{segments.map(s=>{
  const x=xAt(s.start_tick),w=xAt(s.end_tick)-x,y=yAt((s.start_tick+s.end_tick)/2)-38;
  const detail=`${s.display_name} · ${s.role_label}${s.partial?'（局部）':''} · ${s.start_tick/480}–${s.end_tick/480} 拍 · ${emotions[s.emotion]?.[0]||''}${s.memory?' · 记忆积木':''}`;
  return <g className={'result-block role-'+s.role} key={s.id} data-role={s.role} tabIndex={0} role="img" aria-label={detail} onFocus={()=>onInspect(detail)} onMouseEnter={()=>onInspect(detail)} onClick={()=>onInspect(detail)}>
   <title>{detail}</title>
   <rect x={x+1} y={y} width={Math.max(1,w-2)} height={76} rx={5} fill={emotions[s.emotion]?.[1]||'var(--blank)'}/>
   <svg x={x+3} y={y+3} width={Math.max(1,w-6)} height={70} overflow="hidden">
    {w>=65?<><text className="result-name" x={5} y={12}>{s.display_name}</text>
     <text className="result-role" x={5} y={27}>{s.role_label}{s.partial&&w>100?' · 局部':''}</text>
     <text className="result-emotion" x={5} y={40}>{emotions[s.emotion]?.[0].split('／')[0]}</text>
     <g transform="translate(2 45)" color="#365052">{melody(s,Math.max(8,w-10))}</g></>
     :<text className="result-role" x={(w-6)/2} y={14} textAnchor="middle">{[...(s.role==='bridge'?'桥接':s.role_label)].map((char,i)=><tspan key={i} x={(w-6)/2} dy={i?12:0}>{char}</tspan>)}</text>}
   </svg>
   {s.memory&&<g pointerEvents="none"><rect x={x+6} y={Math.max(0,y-17)} width={50} height={17} rx={3} fill="var(--text)"/><text x={x+11} y={Math.max(0,y-17)+12} fontSize={10} fill="var(--surface)">记忆积木</text></g>}
  </g>
 })}</>
}
