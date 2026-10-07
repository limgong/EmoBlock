"""Small dependency-free Tk bitmap resources, scaled with native Tk points."""
import math
import tkinter as tk


def scale(root):
    return max(.75,float(root.tk.call('tk','scaling'))/(4/3))


def pixels(root,value):return max(1,round(value*scale(root)))


def rgb(color):return tuple(int(color[i:i+2],16) for i in (1,3,5))


def blend(a,b,amount):
    return '#'+''.join(f'{round(x+(y-x)*amount):02x}' for x,y in zip(rgb(a),rgb(b)))


def bitmap(root,size,color_at):
    image=tk.PhotoImage(master=root,width=size,height=size)
    image.put(' '.join('{'+ ' '.join(color_at(x,y) for x in range(size))+'}' for y in range(size)))
    return image


def round_distance(x,y,box,r):
    a,b,c,d=box
    qx=abs(x-(a+c)/2)-(c-a)/2+r;qy=abs(y-(b+d)/2)-(d-b)/2+r
    return math.hypot(max(0,qx),max(0,qy))+min(max(qx,qy),0)-r


def blurred_shadow():
    mask=[[float(round_distance(x+.5,y+.5,(3,5,40,42),9)<=0) for x in range(44)] for y in range(44)]
    weights=[math.exp(-i*i/(2*1.2**2)) for i in range(-4,5)];weights=[v/sum(weights) for v in weights]
    rows=[[sum(mask[y][x+i]*v for i,v in zip(range(-4,5),weights) if 0<=x+i<44) for x in range(44)] for y in range(44)]
    return [[sum(rows[y+i][x]*v for i,v in zip(range(-4,5),weights) if 0<=y+i<44) for x in range(44)] for y in range(44)]


SHADOW=blurred_shadow()


def surface_image(root,palette,role,state):
    background=palette['bg'] if role=='Header' else palette['panel']
    normal=palette['accent'] if role=='Primary' and palette['bg']!='#1c1c1e' else palette['inset']
    fill=palette['selected'] if state=='pressed' and role!='Primary' else normal
    if state=='disabled':fill=palette['inset']
    border=palette['accent'] if state in ('active','focus','selected') else palette['line']
    if state=='pressed':border=palette['ink']
    size=pixels(root,44)
    def color(x,y):
        x=(x+.5)*44/size;y=(y+.5)*44/size
        distance=round_distance(x,y,(1,1,42,40),9)
        base=background
        if palette['bg']!='#1c1c1e' and role!='Header':
            alpha=SHADOW[min(43,int(y))][min(43,int(x))]
            base=blend(background,palette['shadow'],alpha)
        if distance<0:return blend(border,fill,min(1,max(0,-distance)))
        return blend(base,border,max(0,1-distance))
    return bitmap(root,size,color)
