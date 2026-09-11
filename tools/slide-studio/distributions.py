"""Sample summaries, equal-width histograms and Tukey box plots."""
import math
import statistics

KINDS={'descriptive':'Descriptive statistics','histogram':'Histogram','boxplot':'Box plot'}

def percentile(values,p):
    ordered=sorted(values);position=(len(ordered)-1)*p
    lo=math.floor(position);hi=math.ceil(position)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)

def summary(values):
    n=len(values);q1=percentile(values,.25);q3=percentile(values,.75);iqr=q3-q1
    inside=[v for v in values if q1-1.5*iqr<=v<=q3+1.5*iqr]
    return dict(n=n,mean=statistics.mean(values),median=statistics.median(values),minimum=min(values),maximum=max(values),
                sd=statistics.stdev(values) if n>1 else None,q1=q1,q3=q3,p90=percentile(values,.9),p95=percentile(values,.95),
                iqr=iqr,low=min(inside),high=max(inside),outliers=[v for v in values if v<q1-1.5*iqr or v>q3+1.5*iqr])

def analyze(s):
    kind=s['chartType'];rows=[line.split('|') for line in s['content'].splitlines() if line.strip()]
    if not 1<=len(rows)<=100:raise ValueError('Enter 1–100 complete observations.')
    width=2 if kind=='boxplot' else 1
    if any(len(r)!=width or any(not v.strip() for v in r) for r in rows):
        raise ValueError('Enter a group and numeric value on each row.' if width==2 else 'Enter one numeric value per row.')
    groups={}
    for row in rows:
        try:
            v=float(row[-1])
            if not math.isfinite(v) or abs(v)>1e12:raise ValueError()
        except ValueError:raise ValueError('Values must be finite numbers between -1e12 and 1e12.')
        name=row[0].strip() if width==2 else 'Values'
        if len(name)>24:raise ValueError('Group names must be at most 24 characters.')
        groups.setdefault(name,[]).append(v)
    if len(groups)>4:raise ValueError('Box plots support up to four groups.')
    if kind=='boxplot':return dict(kind=kind,groups=[dict(name=k,values=v,**summary(v)) for k,v in groups.items()])
    values=groups['Values'];a=dict(kind=kind,values=values,**summary(values))
    if kind=='histogram':
        bins=s.get('histogramBins','auto')
        if bins!='auto' and (isinstance(bins,bool) or not isinstance(bins,int) or not 2<=bins<=12):raise ValueError('Choose automatic bins or 2–12 bins.')
        count=min(12,max(2,math.ceil(math.sqrt(len(values))))) if bins=='auto' else bins
        lo,hi=min(values),max(values)
        if lo==hi:
            padding=max(1,abs(lo)*.01);lo-=padding;hi+=padding;count=1
        edges=[lo+(hi-lo)*i/count for i in range(count+1)];counts=[0]*count
        for v in values:counts[min(count-1,max(0,math.floor((v-lo)/(hi-lo)*count)))]+=1
        a.update(edges=edges,counts=counts)
    return a

def draw(a,rect,line,txt,dot):
    fmt=lambda v:'N/A' if v is None else f'{v:.5g}'
    if a['kind']=='descriptive':
        items=[('Count',a['n']),('Mean',a['mean']),('Median',a['median']),('Sample standard deviation',a['sd']),
               ('Minimum',a['minimum']),('Maximum',a['maximum']),('25th percentile (Q1)',a['q1']),('75th percentile (Q3)',a['q3']),
               ('Interquartile range',a['iqr']),('90th percentile',a['p90']),('95th percentile',a['p95']),('Potential outliers',len(a['outliers']))]
        for i,(name,v) in enumerate(items):
            x=80+(i//6)*550;y=220+(i%6)*57
            rect(x,y,510,51,'panel');txt(name,x+14,y+13,340,19);txt(fmt(v),x+355,y+10,155,22,'accent',True)
        txt('Sample SD uses n − 1; N/A for one value. Percentiles use linear interpolation.',80,579,1050,17,'muted')
        txt('Potential outliers fall beyond Q1 − 1.5 × IQR or Q3 + 1.5 × IQR.',80,606,1050,17,'muted')
    elif a['kind']=='histogram':
        counts=a['counts'];edges=a['edges'];step=900/len(counts);maximum=max(counts)
        tick=max(1,math.ceil(maximum/5));top=tick*5
        txt(f'n = {a["n"]}     Mean = {fmt(a["mean"])}     Median = {fmt(a["median"])}',140,205,970,22,'text',True)
        for j in range(6):
            y=535-j*51;line(140,y,1040,y,'panel',1);txt(j*tick,70,y-10,70,16)
        txt('Frequency',60,246,150,17)
        for i,v in enumerate(counts):
            h=v/top*255;x=140+i*step;rect(x+1,535-h,step-2,h,'accent');txt(v,x+step/2-7,510-h,80,16)
        # Alternate labels when bins are narrow to prevent overlap.
        stride=2 if len(counts)>6 else 1
        for i,edge in enumerate(edges):
            if i%stride==0 or i==len(counts):txt(f'{edge:.4g}',140+i*step-20,546,100,15)
        txt(f'{len(counts)} equal-width bins. Intervals include the left edge; the final bin also includes the maximum.',80,592,1060,17,'muted')
    else:
        groups=a['groups'];low=min(min(g['values']) for g in groups);high=max(max(g['values']) for g in groups)
        pad=(high-low)*.08 or max(1,abs(low)*.01);low-=pad;high+=pad
        px=lambda v:300+(v-low)/(high-low)*740
        txt('Distribution by group',100,205,950,22,'text',True)
        for i in range(6):
            v=low+(high-low)*i/5;x=px(v);line(x,260,x,535,'panel',1);txt(f'{v:.4g}',x-22,546,115,16)
        step=260/len(groups)
        for i,g in enumerate(groups):
            y=265+(i+.5)*step
            txt(g['name'],80,y-24,220,17,'text',True);txt(f'n = {g["n"]}',80,y+2,220,16,'muted')
            line(px(g['low']),y,px(g['high']),y,'accent',2)
            line(px(g['low']),y-12,px(g['low']),y+12,'accent');line(px(g['high']),y-12,px(g['high']),y+12,'accent')
            rect(px(g['q1']),y-18,max(1,px(g['q3'])-px(g['q1'])),36,'panel')
            line(px(g['q1']),y-18,px(g['q3']),y-18,'accent');line(px(g['q1']),y+18,px(g['q3']),y+18,'accent')
            line(px(g['q1']),y-18,px(g['q1']),y+18,'accent');line(px(g['q3']),y-18,px(g['q3']),y+18,'accent')
            line(px(g['median']),y-18,px(g['median']),y+18,'accent',3)
            for v in g['outliers']:dot(px(v),y,'EF4444')
        txt('Box: Q1–Q3. Center line: median. Whiskers: observed values within 1.5 × IQR.',80,585,1070,17,'muted')
        txt('Red points: potential outliers (retained). Quartiles use linear interpolation.',80,609,1070,17,'muted')
