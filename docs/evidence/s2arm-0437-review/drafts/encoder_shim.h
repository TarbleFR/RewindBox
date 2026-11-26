#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>
#include <string.h>
#include "rb_draw_fast_rule.h"
typedef uintptr_t id;
typedef size_t NSUInteger;
typedef int MTLCullMode, MTLWinding, MTLTriangleFillMode;
typedef struct { double originX,originY,width,height,znear,zfar; } MTLViewport;
typedef struct { size_t x,y,width,height; } MTLScissorRect;
typedef struct { char key[8]; } NvShader;
typedef struct { int x,y,w,h; } p_scissor;
static struct {uint32_t st_ref[2]; int has_vp,depth_clamp; float vp[1][4],dr[2],blend_color[4]; uint8_t vp_sw[1][4]; struct {int df;} ds; struct {int front,cull,mode,offset_en;} poly; struct {float units,factor,clamp;} po;} S;
static struct {int has_sc; p_scissor sc;} R;
static struct {double rs;size_t tw,th;int hd,hs;uint64_t serial;} g_pass={1.0,1920,1080,1,0,1};
static struct {unsigned ok; uint32_t sref[2]; MTLViewport vp; MTLScissorRect sc; int cull,wind,fill,clip,origin_ll,rast_flip; float bias[3],blend[4]; } g_ed;
enum {ED_SREF=1,ED_VP=2,ED_SC=4,ED_CULL=8,ED_WIND=16,ED_FILL=32,ED_BIAS=64,ED_CLIP=128,ED_BLEND=256};
enum {NVN_FACE_FRONT_AND_BACK=3,NVN_FACE_FRONT=1,NVN_FACE_BACK=2,NVN_POLYGON_MODE_LINE=1,NVN_FRONT_FACE_CCW=1, MTLCullModeFront=1,MTLCullModeBack=2,MTLCullModeNone=0,MTLWindingCounterClockwise=1,MTLWindingClockwise=0,MTLTriangleFillModeLines=1,MTLTriangleFillModeFill=0};
static unsigned g_rb_ed_dirty=511;
static int g_wd,g_wd_mode, g_dss_dirty=1, s2a_nvn_rast_flip;
static _Atomic int g_origin_ll;
static id g_enc_dss;
static id dss_get(int d,int s){return 1+S.ds.df+d*16+s*32;}
#define wd_tr_on() 0
#define MLOG(...)
#define PD(...)
#define RED_ONCE(...)
static void s2a_widen_map_viewport(int m,float*x,float*w){*x+=m;*w*=2;}
static void s2a_widen_map_viewport_y(int m,float*y,float*h){*y-=m;*h*=2;}
static void s2a_widen_map_scissor(int m,int*x,int*w){*x+=m;*w*=2;}
static void s2a_widen_map_scissor_y(int m,int*y,int*h){*y-=m;*h*=2;}
static void rs_rect(double rs,long*x,long*y,long*w,long*h){*x*=rs;*y*=rs;*w*=rs;*h*=rs;}
static void rb_scale_viewport(double rs,double*x,double*y,double*w,double*h){*x*=rs;*y*=rs;*w*=rs;*h*=rs;}
#define ONE(f,tag,type) static void f(id e,type v){fputc(tag,stdout);fwrite(&v,sizeof v,1,stdout);}
ONE(enc_r_dss,1,id)
ONE(enc_r_viewport,2,MTLViewport)
ONE(enc_r_scissor,3,MTLScissorRect)
ONE(enc_r_winding,4,int)
ONE(enc_r_cull,5,int)
ONE(enc_r_fill,6,int)
ONE(enc_r_depth_clip,7,int)
static void enc_r_stencil_ref(id e,uint32_t a,uint32_t b){uint32_t v[]={a,b};fputc(8,stdout);fwrite(v,sizeof v,1,stdout);}
static void enc_r_depth_bias(id e,float a,float b,float c){float v[]={a,b,c};fputc(9,stdout);fwrite(v,sizeof v,1,stdout);}
static void enc_r_blend_color(id e,float a,float b,float c,float d){float v[]={a,b,c,d};fputc(10,stdout);fwrite(v,sizeof v,1,stdout);}
