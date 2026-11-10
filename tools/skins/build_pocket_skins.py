#!/usr/bin/env python3
"""Reconstruct RewindBox's two original Pocket skins after workspace maintenance.

The recovered v1 layout is adapted to the approved raw imagegen body photographs.
Control sprites are new deterministic distance-field renders from pocket_art.py;
these outputs are not claimed identical to the lost prepared commit. No third-party
skin or game artwork is included. Requires the pinned Pillow/numpy dependencies.
Run from any directory; --output and --body-textures override the default paths.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, zipfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pocket_art import control, base, knob
import screen_opening

SCALE = 3
ROOT = Path(__file__).resolve().parents[2]
FONT = Path(__file__).resolve().parent / 'fonts' / 'DejaVuSans.ttf'
BOLD = Path(__file__).resolve().parent / 'fonts' / 'DejaVuSans-Bold.ttf'
LICENSE_LABEL = 'Original RewindBox artwork; third-party marks excluded'
LICENSE = """Original artwork and layouts prepared for RewindBox.
Body photographs were generated for this project and are embedded unchanged.
Control artwork is an original reconstruction after workspace maintenance.
No third-party skin or game artwork is included. Console names and trademarks
belong to their respective owners. No third-party rights are granted.
Publication licensing is to be set by the project maintainer.
"""
RECONSTRUCTION = {
    'status': 'reconstructed-after-workspace-maintenance',
    'geometrySource': 'RewindBox_Pocket_Collection_v1.zip / Sources/Approved_Pocket',
    'controls': 'new deterministic distance-field renders; not recovered original bytes',
    'bodyTextures': 'approved raw images; only the game window and 7 points around it are redrawn at 4:3 (screen_opening.reframe), per layout',
    'layoutVersion': 4,
    'gameScreen': 'the opening drawn on the body, redrawn at the game\'s 4:3 from the raw image (screen_opening.reframe); cutout shipped as screens/*.png, outputFrame exactly 4:3',
}



def rect(x,y,w,h): return dict(x=x,y=y,width=w,height=h)
def frame(item): return item['frame']
def box(r): return (r['x'],r['y'],r['x']+r['width'],r['y']+r['height'])
def intersect(a,b):
    a,b=box(a),box(b)
    return max(a[0],b[0]) < min(a[2],b[2])-0.01 and max(a[1],b[1]) < min(a[3],b[3])-0.01

def button(name,x,y,w,h):
    return {'frame':rect(x,y,w,h),'inputs':[name], 'asset':{'normal':f'controls/{name}.png','pressed':f'controls/{name}-pressed.png'},'extendedEdges':dict(top=0,bottom=0,left=0,right=0)}
def dpad(x,y,size):
    return {'frame':rect(x,y,size,size),'inputs':{d:d for d in ['up','down','left','right']},'asset':{'normal':'controls/dpad.png','pressed':'controls/dpad-pressed.png'},'extendedEdges':dict(top=0,bottom=0,left=0,right=0)}
def stick(x,y,size,side='left'):
    name='main' if side=='left' else 'cstick'
    return {'frame':rect(x,y,size,size),'inputs':{d:f'{side}Thumbstick{d.title()}' for d in ['up','down','left','right']},'asset':{'normal':f'controls/{name}-base.png','pressed':f'controls/{name}-base-pressed.png'},'thumbstick':{'name':f'controls/{name}-knob.png','width':round(size*.62,2),'height':round(size*.62,2)},'extendedEdges':dict(top=0,bottom=0,left=0,right=0)}

def layout(console, display, orientation):
    edge=display=='edgeToEdge'; portrait=orientation=='portrait'
    W,H=(393,852) if edge and portrait else (852,393) if edge else (375,667) if portrait else (667,375)
    screen=rect(8,76,377,282.75) if edge and portrait else rect(216,30,420,315) if edge else rect(39,60,296,222) if portrait else rect(166,50,336,252)
    b=button
    if console=='wii' and edge and portrait:
        items=[b('c',34,398,56,48),b('z',303,398,56,48),stick(30,466,108),b('a',258,460,88,88),b('b',258,564,88,52),dpad(36,625,100),b('one',238,660,56,56),b('two',310,660,56,56),b('minus',30,752,56,48),b('home',122,752,56,48),b('plus',214,752,56,48),b('menu',306,752,56,48)]
    elif console=='wii' and edge:
        items=[b('c',66,18,60,48),b('z',138,18,60,48),stick(76,84,112),dpad(82,213,100),b('menu',66,321,56,48),b('minus',644,18,48,48),b('home',694,18,48,48),b('plus',744,18,48,48),b('a',690,83,88,88),b('b',690,188,88,54),b('one',650,263,60,60),b('two',722,263,60,60)]
    elif console=='wii' and portrait:
        items=[b('c',26,320,56,44),b('z',293,320,56,44),stick(28,377,94),b('a',257,375,76,76),b('b',257,461,76,48),dpad(32,484,90),b('one',235,530,52,52),b('two',303,530,52,52),b('minus',24,606,48,44),b('home',116,606,48,44),b('plus',208,606,48,44),b('menu',300,606,48,44)]
    elif console=='wii':
        items=[b('c',10,20,56,44),b('z',78,20,56,44),stick(24,82,96),dpad(26,197,92),b('menu',14,311,48,44),b('minus',527,20,44,44),b('home',573,20,44,44),b('plus',619,20,44,44),b('a',565,78,76,76),b('b',565,166,76,48),b('one',535,237,52,52),b('two',601,237,52,52)]
    elif edge and portrait:
        items=[b('l',26,392,88,48),b('r',279,392,88,48),b('y',198,452,68,48),b('z',303,453,48,48),b('x',335,512,48,72),b('a',254,515,76,76),b('b',198,566,48,48),stick(30,465,108),dpad(38,633,96),stick(249,637,96,'right'),b('start',171,752,56,48),b('menu',30,752,56,48)]
    elif edge:
        items=[b('l',66,18,64,48),b('menu',138,18,60,48),stick(76,84,112),dpad(80,218,100),b('start',138,321,60,48),b('r',650,18,64,48),b('z',726,18,64,48),b('y',644,78,60,48),b('x',730,78,60,48),b('a',705,135,76,76),b('b',646,195,48,48),stick(682,260,100,'right')]
    elif portrait:
        items=[b('l',26,320,80,44),b('r',269,320,80,44),b('y',190,373,60,44),b('z',305,373,44,44),b('x',321,429,44,62),b('a',249,429,66,66),b('b',194,479,44,44),stick(28,377,94),dpad(32,484,90),stick(245,537,90,'right'),b('start',159,606,48,44),b('menu',24,606,48,44)]
    else:
        items=[b('l',10,20,56,44),b('menu',78,20,56,44),stick(24,82,96),dpad(26,197,92),b('start',78,311,56,44),b('r',533,20,56,44),b('z',601,20,56,44),b('y',532,82,52,44),b('x',601,82,52,44),b('a',577,136,72,72),b('b',529,188,44,44),stick(557,257,96,'right')]
    filename=f'body-{orientation}.png'
    return {'assets':{'small':filename,'medium':filename,'large':filename},'mappingSize':{'width':W,'height':H},'screens':[{'outputFrame':screen}],'items':items,'translucent':False}


def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else FONT),max(8,int(size)))
def gradient(size,top,bottom,radial=False):
    w,h=size
    y=np.linspace(0,1,h,dtype=np.float32)[:,None,None]
    a=np.array(top)[None,None,:]*(1-y)+np.array(bottom)[None,None,:]*y
    a=np.tile(a,(1,w,1))
    if radial:
        yy,xx=np.mgrid[:h,:w];r=np.sqrt(((xx-w*.35)/w)**2+((yy-h*.2)/h)**2)[...,None]
        a=np.clip(a+(0.5-r)*20,0,255)
    alpha=np.full((h,w,1),255,dtype=np.uint8)
    return Image.fromarray(np.concatenate((a.astype(np.uint8),alpha),axis=2),'RGBA')
def pxbox(r,s=SCALE):return tuple(round(v*s) for v in box(r))
def rounded(im,r,fill,radius,outline=None,width=1):
    ImageDraw.Draw(im).rounded_rectangle(pxbox(r),round(radius*SCALE),fill=fill,outline=outline,width=max(1,round(width*SCALE)))
def centered(draw,xy,text,sz,fill,bold=False):
    draw.text(xy,text,font=font(sz,bold),anchor='mm',fill=fill)


def png(im):
    out=io.BytesIO();im.save(out,format='PNG',compress_level=9);return out.getvalue()
def compose(L, files, pressed=False):
    W,H=L['mappingSize'].values()
    im=Image.open(io.BytesIO(files[L['assets']['large']])).convert('RGBA').resize((W*SCALE,H*SCALE),Image.Resampling.LANCZOS)
    # With a cutout (screens[].screenCutout) the game shows through the body's own opening:
    # the preview keeps the navy window as drawn. Without one (PS2 Pocket's rectangular
    # window) the declared rectangle is the game's place.
    if 'screenCutout' not in L['screens'][0]:
        d=ImageDraw.Draw(im);bb=pxbox(L['screens'][0]['outputFrame'])
        d.rectangle((bb[0],bb[1],bb[2]-1,bb[3]-1),fill=(9,22,49,255))
    for item in L['items']:
        f=item['frame'];b=pxbox(f)
        asset=item['asset']['pressed' if pressed else 'normal']
        a=Image.open(io.BytesIO(files[asset])).convert('RGBA').resize((b[2]-b[0],b[3]-b[1]),Image.Resampling.LANCZOS)
        im.alpha_composite(a,(b[0],b[1]))
        if 'thumbstick' in item:
            th=item['thumbstick'];w,h=round(th['width']*SCALE),round(th['height']*SCALE)
            k=Image.open(io.BytesIO(files[th['name']])).convert('RGBA').resize((w,h),Image.Resampling.LANCZOS)
            x=(b[0]+b[2]-w)//2+(round(f['width']*.12*SCALE) if pressed else 0)
            y=(b[1]+b[3]-h)//2-(round(f['height']*.10*SCALE) if pressed else 0)
            im.alpha_composite(k,(x,y))
    return im


def validate(console,reps,files):
    expected=set(['a','b','one','two','plus','minus','home','c','z','menu','up','down','left','right'] if console=='wii' else ['a','b','x','y','z','l','r','start','menu','up','down','left','right'])
    expected.update(f'leftThumbstick{d}' for d in ['Up','Down','Left','Right'])
    if console=='gc':expected.update(f'rightThumbstick{d}' for d in ['Up','Down','Left','Right'])
    result=[]
    for display,orientations in reps.items():
        for orientation,L in orientations.items():
            W,H=L['mappingSize'].values();screen=L['screens'][0]['outputFrame'];provided=set();minsize=999
            for i,item in enumerate(L['items']):
                f=item['frame'];b=box(f);assert 0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=H,(console,display,orientation,i,'bounds')
                assert not intersect(f,screen),(console,display,orientation,i,'screen')
                for prev in L['items'][:i]:assert not intersect(f,prev['frame']),(console,display,orientation,i,'overlap',prev['frame'])
                minsize=min(minsize,f['width'],f['height']);inputs=item['inputs'];provided.update(inputs if isinstance(inputs,list) else inputs.values())
                for p in item['asset'].values():assert p in files
                assert files[item['asset']['normal']]!=files[item['asset']['pressed']]
                if 'thumbstick' in item:assert item['thumbstick']['name'] in files
            assert expected<=provided,(console,display,orientation,expected-provided)
            # The game's container is the opening the body draws, not a hand-placed rectangle.
            body=Image.open(io.BytesIO(files[L['assets']['large']]));cov=screen_opening.coverage_of(files[L['screens'][0]['screenCutout']])
            assert cov.shape==(body.height,body.width) and screen==screen_opening.native_frame(cov,(W,H),4/3),(console,display,orientation,'opening')
            assert abs(screen['width']/screen['height']-4/3)<1e-4,(console,display,orientation,'4:3')
            if display=='edgeToEdge':
                for aw,ah in [(375,812),(390,844),(393,852),(430,932)]:
                    if orientation=='landscape':aw,ah=ah,aw
                    assert minsize*min(aw/W,ah/H)>=44,(console,orientation,aw,ah,minsize)
                if orientation=='portrait':assert all(box(i['frame'])[1]>=65 and box(i['frame'])[3]<=H-35 for i in L['items'])
                else:assert all(box(i['frame'])[0]>=60 and box(i['frame'])[2]<=W-60 and box(i['frame'])[3]<=H-24 for i in L['items'])
            else:assert minsize>=44
            result.append({'display':display,'orientation':orientation,'size':[W,H],'items':len(L['items']),'smallestTargetPoints':minsize})
    return result


def read_body(body_dir, orientation):
    candidates=[body_dir/f'body-{orientation}.png',body_dir/f'edgeToEdge-{orientation}.png',body_dir/'wii'/f'edgeToEdge-{orientation}.png']
    p=next((p for p in candidates if p.is_file()),None)
    if p is None: raise FileNotFoundError(f'Raw {orientation} body is missing in {body_dir}')
    data=p.read_bytes()
    with Image.open(io.BytesIO(data)) as im: im.verify()
    return data


def archive(target,files):
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,data in sorted(files.items()):
            assert not path.startswith('/') and '..' not in Path(path).parts
            zi=zipfile.ZipInfo(path,(2026,11,3,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED
            zi.create_system=3;zi.external_attr=0o100644<<16
            z.writestr(zi,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for path in z.namelist():
            if path.endswith('.png'):
                with Image.open(io.BytesIO(z.read(path))) as im: im.verify()


def build(out,body_dir):
    out.mkdir(parents=True,exist_ok=True);entries=[];receipts={};bodies_cache={}
    raw_bodies={f'body-{o}.png':read_body(body_dir,o) for o in ['portrait','landscape']}
    for console,pid,name in [('wii','wii-pocket','Wii Pocket'),('gc','gamecube-pocket','GameCube Pocket – Ivory')]:
        reps={display:{orientation:layout(console,display,orientation) for orientation in ['portrait','landscape']} for display in ['edgeToEdge','standard']}
        files={'LICENSE.txt':LICENSE.encode()};names=set()
        # The game's container: the opening the body draws, redrawn at the game's 4:3
        # (screen_opening.reframe): one body and one cutout per layout, because the
        # home-button layouts show the same raw image scaled differently on each axis.
        for orientation in ['portrait','landscape']:
            raw=Image.open(io.BytesIO(raw_bodies[f'body-{orientation}.png'])).convert('RGB')
            hand=reps['edgeToEdge'][orientation];W0,H0=hand['mappingSize'].values();r=hand['screens'][0]['outputFrame']
            cov=screen_opening.opening(raw,((r['x']+r['width']/2)*raw.width/W0,(r['y']+r['height']/2)*raw.height/H0))
            for display in reps:
                L=reps[display][orientation];mapping=tuple(L['mappingSize'].values())
                key=bodies_cache.get((orientation,display))
                if key is None:
                    body,_,changed=screen_opening.reframe(raw,cov,mapping,4/3)
                    nc=screen_opening.opening(body,((r['x']+r['width']/2)*raw.width/W0,(r['y']+r['height']/2)*raw.height/H0))
                    key=bodies_cache[(orientation,display)]=(png(body),screen_opening.cutout(nc),screen_opening.native_frame(nc,mapping,4/3),changed)
                # The controls are separate rendered sprites (the body carries none): the frame
                # brought forward may pass under their transparent margins; the verifier still
                # checks that no control or touch area reaches the new window.
                suffix='' if display=='edgeToEdge' else 'standard-'
                files[f'body-{suffix}{orientation}.png']=key[0]
                files[f'screens/{suffix}{orientation}.png']=key[1]
                name=f'body-{suffix}{orientation}.png'
                L['assets']={'small':name,'medium':name,'large':name}
                L['screens']=[{'outputFrame':key[2],'screenCutout':f'screens/{suffix}{orientation}.png'}]
        for orientations in reps.values():
            for L in orientations.values():
                for item in L['items']:
                    if isinstance(item['inputs'],list):names.update(item['inputs'])
        for n in sorted(names|{'dpad'}):
            for held in [False,True]:files[f'controls/{n}{"-pressed" if held else ""}.png']=png(control(n,console,held))
        for n in ['main']+(['cstick'] if console=='gc' else []):
            for held in [False,True]:files[f'controls/{n}-base{"-pressed" if held else ""}.png']=png(base(held,cstick=n=='cstick'))
            files[f'controls/{n}-knob.png']=png(knob(n=='cstick'))
        for orientation in ['portrait','landscape']:
            image=png(compose(reps['edgeToEdge'][orientation],files))
            files[f'previews/{orientation}.png']=image
            (out/f'{pid}-{orientation}.png').write_bytes(image)
            (out/f'{pid}-{orientation}-pressed.png').write_bytes(png(compose(reps['edgeToEdge'][orientation],files,pressed=True)))
            (out/f'{pid}-standard-{orientation}.png').write_bytes(png(compose(reps['standard'][orientation],files)))
        info={'name':name,'identifier':f'org.rewindbox.{pid}','author':'RewindBox','gameTypeIdentifier':f'public.aoshuang.game.{"wii" if console=="wii" else "ngc"}','version':4,'license':LICENSE_LABEL,'previewImages':{o:f'previews/{o}.png' for o in ['portrait','landscape']},'provenance':RECONSTRUCTION,'representations':{'iphone':reps}}
        files['info.json']=(json.dumps(info,indent=2,ensure_ascii=False)+'\n').encode()
        checks=validate(console,reps,files)
        for path,data in files.items():
            if path.endswith('.png'):
                with Image.open(io.BytesIO(data)) as im:im.verify()
        target=out/f'{pid}.manicskin';archive(target,files)
        entry={'id':pid,'name':name,'console':console,'archiveAsset':f'assets/skins/pocket/{pid}.manicskin','sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'size':target.stat().st_size,'previewAssets':{o:f'assets/skins/pocket/{pid}-{o}.png' for o in ['portrait','landscape']},'author':'RewindBox','license':LICENSE_LABEL}
        entries.append(entry)
        receipts[pid]={'layouts':checks,'archiveSha256':entry['sha256'],'archiveBytes':entry['size'],'files':{p:{'sha256':hashlib.sha256(d).hexdigest(),'bytes':len(d)} for p,d in sorted(files.items())},'physicalDeviceTested':False}
    (out/'catalog.json').write_text(json.dumps({'schemaVersion':1,'skins':entries},ensure_ascii=False,indent=2)+'\n')
    (out/'validation.json').write_text(json.dumps({'generator':'tools/skins/build_pocket_skins.py','scale':SCALE,'provenance':RECONSTRUCTION,'checks':'PNG CRC; ZIP paths; complete input maps; asset presence and states; no overlaps; game screen = the opening drawn on the body; point-size matrix; built-in safe margins','physicalDeviceTested':False,'skins':receipts},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(out),'skins':entries},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'assets/skins/pocket')
    parser.add_argument('--body-textures',type=Path,default=Path(__file__).resolve().parent/'body-textures')
    args=parser.parse_args();build(args.output,args.body_textures)
