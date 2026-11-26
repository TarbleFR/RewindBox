static uint32_t rnd(void){static uint32_t r=5721339;r^=r<<13;r^=r>>17;r^=r<<5;return r;}
int main(void){
    static NvShader f={"test"};
    R.sc=(p_scissor){18,20,960,540};R.has_sc=1;S.dr[1]=1;
    for(unsigned i=0;i<200000;i++){
        uint32_t v=rnd();
        switch(v%25){
        case 0: g_pass.serial++; g_ed.ok=0; g_enc_dss=0;g_pass.rs=(rnd()&1)?1:1.5;g_pass.tw=640+(rnd()%1440);g_pass.th=360+(rnd()%900);break;
        case 1: S.has_vp=rnd()&1;for(int j=0;j<4;j++)S.vp[0][j]=(int)(rnd()%2000)-128;g_rb_ed_dirty|=ED_VP;break;
        case 2: S.dr[0]=(rnd()%100)*0.01f;S.dr[1]=(rnd()%100)*0.01f;g_rb_ed_dirty|=ED_VP;break;
        case 3:{uint32_t k=rnd()&1?0x100:0;memcpy(S.vp_sw[0],&k,4);g_rb_ed_dirty|=ED_VP;break;}
        case 4:R.has_sc=rnd()&1;R.sc=(p_scissor){(int)(rnd()%2000)-128,(int)(rnd()%1200)-128,rnd()%1024,rnd()%512};g_rb_ed_dirty|=ED_SC;break;
        case 5:g_wd=rnd()&1;g_wd_mode=rnd()%4;break;
        case 6:g_origin_ll=rnd()&1;break;
        case 7:s2a_nvn_rast_flip=rnd()&1;break;
        case 8:S.poly.front=rnd()&1;S.poly.cull=rnd()&3;S.poly.mode=rnd()&1;S.poly.offset_en=rnd()&4;g_rb_ed_dirty|=ED_CULL|ED_WIND|ED_FILL|ED_BIAS;break;
        case 9:S.po.units=rnd()%8;S.po.factor=rnd()%9;S.po.clamp=rnd()%11;g_rb_ed_dirty|=ED_BIAS;break;
        case 10:for(int j=0;j<4;j++)S.blend_color[j]=rnd()%15;g_rb_ed_dirty|=ED_BLEND;break;
        case 11:S.st_ref[0]=rnd();S.st_ref[1]=rnd();g_rb_ed_dirty|=ED_SREF;break;
        case 12:S.depth_clamp=rnd()&1;g_rb_ed_dirty|=ED_CLIP;break;
        case 13:S.ds.df=rnd()%9;g_dss_dirty=1;break;
        case 14:g_ed.ok=0;break;
        }
        int drawn=draw_pass_state(1,(rnd()&1)?&f:0);
        fputc(drawn?200:201,stdout);
    }
    return ferror(stdout);
}
