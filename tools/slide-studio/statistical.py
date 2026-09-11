"""Deterministic Pareto and Pearson analysis. No external services.

Pearson formula: https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/correlat.htm
All rows are complete observations; missing and non-finite values are rejected.
"""
import math
import distributions

KINDS = {'pareto': 'Pareto', 'correlation': 'Correlation + regression', 'matrix': 'Correlation matrix'}
KINDS.update(distributions.KINDS)

def pearson(x, y):
    mx, my = math.fsum(x)/len(x), math.fsum(y)/len(y)
    dx, dy = [v-mx for v in x], [v-my for v in y]
    xx, yy = math.fsum(v*v for v in dx), math.fsum(v*v for v in dy)
    xy = math.fsum(a*b for a,b in zip(dx,dy))
    r = max(-1., min(1., xy/math.sqrt(xx)/math.sqrt(yy))) if xx and yy else None
    slope = xy/xx if xx else None
    return {'r': r, 'r2': r*r if r is not None else None, 'slope': slope,
            'intercept': my-slope*mx if slope is not None else None}

def analyze(s):
    kind = s['chartType']
    if kind in distributions.KINDS:return distributions.analyze(s)
    rows = [[v.strip() for v in line.split('|')] for line in s['content'].splitlines() if line.strip()]
    maximum = 12 if kind=='pareto' else 100
    minimum = 1 if kind=='pareto' else 3
    if not minimum <= len(rows) <= maximum:
        raise ValueError(f'{KINDS[kind]} needs {minimum}–{maximum} complete rows.')
    width = len(rows[0])
    if (kind!='matrix' and width!=2) or (kind=='matrix' and not 2<=width<=4) or any(len(r)!=width or not all(r) for r in rows):
        raise ValueError('Fill every field. Pareto and correlation need two fields; a matrix needs 2–4 variables per observation.')
    raw_names = s.get('seriesNames','') if kind=='matrix' else ''
    if not isinstance(raw_names,str): raise ValueError('Variable names must be text.')
    names = [v.strip() for v in raw_names.split('|')] if raw_names.strip() else []
    expected = width if kind=='matrix' else 1
    if names and (len(names)!=expected or any(not n or len(n)>24 for n in names)):
        raise ValueError(f'Enter {expected} name(s), each up to 24 characters.')
    names = names or ([f'Variable {i+1}' for i in range(width)] if kind=='matrix' else ['Value'])
    try:
        values = [[float(v) for v in (r[1:] if kind=='pareto' else r)] for r in rows]
        if any(not math.isfinite(v) or abs(v)>1e12 for r in values for v in r): raise ValueError()
    except ValueError:
        raise ValueError('Enter a finite number in every numeric field (between -1e12 and 1e12).')
    if kind=='pareto':
        if any(len(r[0])>24 for r in rows):raise ValueError('Category labels must be at most 24 characters.')
        totals={}
        for row,v in zip(rows,values):
            if v[0]<0:raise ValueError('Pareto values must be nonnegative.')
            totals[row[0]]=totals.get(row[0],0)+v[0]
        ordered=sorted(totals.items(),key=lambda p:-p[1])
        total=math.fsum(totals.values())
        if total<=0:raise ValueError('Pareto values must have a positive total.')
        cumulative=[];running=0
        for _,v in ordered:running+=v;cumulative.append(running/total)
        cutoff=next(i+1 for i,v in enumerate(cumulative) if v>=.8-1e-12)
        return dict(kind=kind,labels=[p[0] for p in ordered],values=[p[1] for p in ordered],cumulative=cumulative,total=total,cutoff=cutoff,n=len(rows))
    columns=list(map(list,zip(*values)))
    if kind=='correlation':
        return dict(kind=kind,x=columns[0],y=columns[1],n=len(rows),**pearson(*columns))
    return dict(kind=kind,names=names,n=len(rows),matrix=[[pearson(x,y)['r'] for y in columns] for x in columns])

def objects(s, theme):
    """Shared editable slide objects; the same geometry drives preview and PPTX."""
    a=analyze(s);out=[]
    def rect(x,y,w,h,color):out.append(dict(kind='rect',x=x,y=y,w=w,h=h,color=theme.get(color,color)))
    def line(x,y,x2,y2,color='muted',width=2):out.append(dict(kind='line',x=x,y=y,w=x2-x,h=y2-y,color=theme.get(color,color),width=width))
    def txt(value,x,y,w=400,size=18,color='text',bold=False):
        out.append(dict(kind='text',x=x,y=y,w=w,h=size*1.4,lines=[str(value)],size=size,color=theme.get(color,color),bold=bold))
    def dot(x,y,color='accent'):out.append(dict(kind='ellipse',x=x-4,y=y-4,w=8,h=8,color=theme.get(color,color)))
    if a['kind'] in distributions.KINDS:
        distributions.draw(a,rect,line,txt,dot)
    elif a['kind']=='pareto':
        n=len(a['labels']);step=840/n;top=max(a['values'])*1.15
        for j in range(6):
            y=520-j*50;line(145,y,985,y,'panel',1)
            txt(f'{top*j/5:.3g}',65,y-10,80,16);txt(f'{j*20}%',1000,y-10,70,16)
        txt('Value',65,225,150,17);txt('Cumulative %',965,225,170,17)
        line(145,320,985,320,'F59E0B',2);txt('80%',1070,309,65,15,'F59E0B')
        points=[]
        for i,(label,v,c) in enumerate(zip(a['labels'],a['values'],a['cumulative'])):
            x=145+(i+.5)*step;y=520-v/top*250
            rect(x-step*.32,y,step*.64,520-y,'accent')
            txt(f'{v:g}',x-step*.3,y-24,step,16)
            # Numbered categories keep long category labels readable in the key.
            txt(str(i+1),x-5,531,step,16)
            points.append((x,520-c*250))
        for p,q in zip(points,points[1:]):line(*p,*q,'10B981',3)
        for p in points:dot(*p,'10B981')
        for i,label in enumerate(a['labels']):
            txt(f'{i+1}. {label}',65+(i%4)*270,560+(i//4)*20,265,15)
        txt(f'Total {a["total"]:g}   •   Top {a["cutoff"]} categories reach {a["cumulative"][a["cutoff"]-1]:.1%}',145,195,970,18,bold=True)
    elif a['kind']=='correlation':
        x,y=a['x'],a['y'];xmin,xmax=min(x),max(x);ymin,ymax=min(y),max(y)
        fit=[]
        if a['slope'] is not None:
            fit=[(v,a['intercept']+a['slope']*v) for v in (xmin,xmax)]
            ymin=min(ymin,*(p[1] for p in fit));ymax=max(ymax,*(p[1] for p in fit))
        xp=(xmax-xmin)*.06 or 1;yp=(ymax-ymin)*.08 or 1
        xmin-=xp;xmax+=xp;ymin-=yp;ymax+=yp
        px=lambda v:145+(v-xmin)/(xmax-xmin)*890
        py=lambda v:530-(v-ymin)/(ymax-ymin)*250
        for j in range(5):
            vx=xmin+(xmax-xmin)*j/4;vy=ymin+(ymax-ymin)*j/4
            line(145,py(vy),1035,py(vy),'panel',1)
            txt(f'{vx:.3g}',px(vx)-18,540,110,16);txt(f'{vy:.3g}',60,py(vy)-9,85,16)
        txt('Y',105,258,40);txt('X',1045,539,40)
        if fit:line(px(fit[0][0]),py(fit[0][1]),px(fit[1][0]),py(fit[1][1]),'10B981',3)
        for xv,yv in zip(x,y):dot(px(xv),py(yv))
        fmt=lambda v:'Undefined' if v is None else f'{v:.4f}'
        txt(f'n = {a["n"]}     Pearson r = {fmt(a["r"])}     R² = {fmt(a["r2"])}',145,205,980,22,bold=True)
        if a['slope'] is not None:
            txt(f'Linear fit: Y = {a["slope"]:.4g} X {a["intercept"]:+.4g}',145,577,950,19)
        else:txt('Linear fit unavailable: X is constant.',145,577,950,19)
        txt('Correlation measures linear association, not causation. Constant variables have undefined r.',145,607,970,15,'muted')
    else:
        n=len(a['names']);cw=150;ch=64;left=335;top=285
        txt(f'Pearson correlation   •   {a["n"]} complete matched observations',120,205,760,22,bold=True)
        for i,name in enumerate(a['names']):
            txt(name,left+i*cw+8,252,cw-12,17,'accent',True)
            txt(name,115,top+i*ch+23,200,17,'accent',True)
            for j,r in enumerate(a['matrix'][i]):
                if j>i: continue
                if i==j: color='E8EDF2';ink='7D8A98'
                elif r is None: color='D1D5DB';ink='64748B'
                else:
                    target=(37,99,235) if r>=0 else (220,38,38)
                    color=''.join(f'{round(248+(v-248)*abs(r)) :02X}' for v in target)
                    ink='FFFFFF' if abs(r)>.55 else '17324D'
                rect(left+j*cw,top+i*ch,cw-8,ch-8,color)
                txt('N/A' if r is None else f'{r:.2f}',left+j*cw+48,top+i*ch+20,85,21,ink,True)
        legend_x=835
        txt('Correlation (r)',legend_x,292,190,17,'accent',True)
        legend=[('1.0  strong positive','053B5C'),('0.3  positive','B7CDE0'),('0.0  none','F8FAFC'),('-0.3  negative','F4C7C9'),('-1.0  strong negative','C91F5B')]
        for i,(label,color) in enumerate(legend):
            rect(legend_x,315+i*30,18,18,color);txt(label,legend_x+30,317+i*30,180,15)
        rect(legend_x,472,18,18,'E8EDF2');txt('Diagonal: self-correlation',legend_x+30,474,200,15)
        txt('What it says:',120,575,95,16,'accent',True)
        # Keep interpretation factual and compact for the exported slide.
        off=[r for i,row in enumerate(a['matrix']) for j,r in enumerate(row) if j<i and r is not None]
        strongest=max((abs(r),r) for r in off)[1] if off else None
        if strongest is None: insight='No variable pair has a defined correlation.'
        elif strongest < -0.7: insight='The strongest pair moves in opposite directions in this sample.'
        elif strongest > 0.7: insight='The strongest pair moves together in this sample.'
        else: insight='The variable pairs show limited linear association in this sample.'
        txt(insight,220,575,750,16)
        txt('Correlation describes linear association. It does not establish causation.',120,606,950,15,'muted')
    return out
