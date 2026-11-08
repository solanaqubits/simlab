use corelib_imports::bounded_int::{BoundedInt as ZB,bounded_int as zq,upcast as zu};
use corelib_imports::bounded_int::bounded_int::SubHelper;
#[inline(always)]
fn rt(w:u128,ia:u128,pow:ZF,_ja:ZF)->u128{
let t:ZF=(w&ia).into();
let wf:ZF=w.into();
((wf-t*0x80000000000001100000000000000000000000000000001)*pow).try_into().unwrap()
}
#[inline(always)]
fn rt1(w: u128, ia: u128) -> u128 {
    let t: ZF = (w & ia).into();
    let wf: ZF = w.into();
    const D: ZF = 0x100000000000002200000000000000000000000000000002;
    (wf + wf - t * D).try_into().unwrap()
}

#[inline(always)]
fn jaa(w:u128,all:Uh)->u128{
zu(zq::sub::<Uh,u128,Tk>(all,w))
}
#[inline(always)]
fn qac(s:[u128;25],all:Uh)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=s;
[a0,a1,a2,a3,a4,a5,a6,a7,jaa(a8,all),a9,a10,a11,a12,a13,jaa(a14,all),a15,jaa(a16,all),a17,a18,a19,a20,a21,jaa(a22,all),a23,a24]
}
type Uh=ZB<0xffffffffffffffffffffffffffffffff,0xffffffffffffffffffffffffffffffff>;
const Ze:Uh=0xffffffffffffffffffffffffffffffff;
impl Tk of SubHelper<Uh,u128>{
type Result=ZB<0,0xffffffffffffffffffffffffffffffff>;
}
#[inline(always)]
pub fn keccak_f1600_x2(s:[u128;25])->[u128;25]{
qac(raa(qac(s,Ze),tb(Zj,1)),Ze)
}
#[inline(always)]
pub fn naa(s:[u128;25])->[u128;25]{
raa(s,tb(Zj,1))
}
#[inline(always)]
pub fn kab(s:[u128;25])->[u128;25]{
raa(s,tbp(Zj))
}
#[inline(always)]
pub fn hab(s:[u128;25])->[u128;25]{
raa(qac(s,Ze),tbm(Zj))
}
#[inline(always)]
pub fn lab(s:[u128;25],rcs:(Box<[u128;13]>,Nullable<[u128;13]>))->[u128;25]{
raa(s,rcs)
}
#[inline(always)]
pub fn rcs()->(Box<[u128;13]>,Nullable<[u128;13]>){
tb(Zj,1)
}
#[inline(always)]
pub fn tb(t:[u128;24],sel:u128)->(Box<[u128;13]>,Nullable<[u128;13]>){
let[c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23]=t;
(BoxTrait::new([c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,1]),NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23,sel]))
}
#[inline(always)]
pub fn tbp(t:[u128;24])->(Box<[u128;13]>,Nullable<[u128;13]>){
let[c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,_]=t;
(BoxTrait::new([c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,1]),NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,0,0]))
}
#[inline(always)]
pub fn tbm(t:[u128;24])->(Box<[u128;13]>,Nullable<[u128;13]>){
let[c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,_]=t;
(BoxTrait::new([c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,1]),NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,0,2]))
}
#[inline(always)]
pub fn g1z()->Box<[u128;13]>{
let[c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,_,_,_,_,_,_,_,_,_,_,_,_]=Zj;
BoxTrait::new([c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,1])
}
#[inline(always)]
pub fn hfull()->Nullable<[u128;13]>{
let[_,_,_,_,_,_,_,_,_,_,_,_,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23]=Zj;
NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23,1])
}
#[inline(always)]
pub fn htbp()->Nullable<[u128;13]>{
let[_,_,_,_,_,_,_,_,_,_,_,_,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,_]=Zj;
NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,0,0])
}
#[inline(always)]
pub fn g1y()->Box<[u128;13]>{
let[c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,_,_,_,_,_,_,_,_,_,_,_,_]=Yx;
BoxTrait::new([c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,1])
}
#[inline(always)]
pub fn hfull_y()->Nullable<[u128;13]>{
let[_,_,_,_,_,_,_,_,_,_,_,_,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23]=Yx;
NullableTrait::new([c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23,1])
}
#[inline(always)]
pub fn rd(s:[u128;25])->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=s;
[a0,a1,a2,a3,a4,a5,a6,a7,jaa(a8,Ze),a9,a10,a11,a12,a13,jaa(a14,Ze),a15,jaa(a16,Ze),a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]
pub fn nt(w:u128)->u128{
jaa(w,Ze)
}
pub(crate) type Zl=Uh;
pub(crate) const Rk:Uh=Ze;
#[inline(always)]
pub(crate) fn rda(s:[u128;25],all:Uh)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=s;
[a0,a1,a2,a3,a4,a5,a6,a7,jaa(a8,all),a9,a10,a11,a12,a13,jaa(a14,all),a15,jaa(a16,all),a17,a18,a19,a20,a21,a22,a23,a24]
}
#[derive(Copy)]
struct Uk{m0:u128}
impl Pr of Destruct<Uk>{
#[inline(always)]
fn destruct(self:Uk) nopanic{let Uk{m0:_}=self;}
}
#[derive(Copy)]
struct Vk{p0:ZF}
impl Qr of Destruct<Vk>{
#[inline(always)]
fn destruct(self:Vk) nopanic{let Vk{p0:_}=self;}
}
#[derive(Copy)]
struct Wk{m1:u128,m2:u128,m3:u128,m4:u128,m5:u128,m6:u128}
impl Rr of Destruct<Wk>{
#[inline(always)]
fn destruct(self:Wk) nopanic{let Wk{m1:_,m2:_,m3:_,m4:_,m5:_,m6:_}=self;}
}
#[derive(Copy)]
struct Xk{p1:ZF,p2:ZF,p3:ZF,p4:ZF,p5:ZF,p6:ZF}
impl Sr of Destruct<Xk>{
#[inline(always)]
fn destruct(self:Xk) nopanic{let Xk{p1:_,p2:_,p3:_,p4:_,p5:_,p6:_}=self;}
}
#[derive(Copy)]
struct Yk{m7:u128,m8:u128,m9:u128,m10:u128,m11:u128,m12:u128}
impl Tr of Destruct<Yk>{
#[inline(always)]
fn destruct(self:Yk) nopanic{let Yk{m7:_,m8:_,m9:_,m10:_,m11:_,m12:_}=self;}
}
#[derive(Copy)]
struct Zk{p7:ZF,p8:ZF,p9:ZF,p10:ZF,p11:ZF,p12:ZF}
impl Ur of Destruct<Zk>{
#[inline(always)]
fn destruct(self:Zk) nopanic{let Zk{p7:_,p8:_,p9:_,p10:_,p11:_,p12:_}=self;}
}
#[derive(Copy)]
struct Pl{m13:u128,m14:u128,m15:u128,m16:u128,m17:u128,m18:u128}
impl Vr of Destruct<Pl>{
#[inline(always)]
fn destruct(self:Pl) nopanic{let Pl{m13:_,m14:_,m15:_,m16:_,m17:_,m18:_}=self;}
}
#[derive(Copy)]
struct Ql{p13:ZF,p14:ZF,p15:ZF,p16:ZF,p17:ZF,p18:ZF}
impl Wr of Destruct<Ql>{
#[inline(always)]
fn destruct(self:Ql) nopanic{let Ql{p13:_,p14:_,p15:_,p16:_,p17:_,p18:_}=self;}
}
#[derive(Copy)]
struct Rl{m19:u128,m20:u128,m21:u128,m22:u128,m23:u128}
impl Xr of Destruct<Rl>{
#[inline(always)]
fn destruct(self:Rl) nopanic{let Rl{m19:_,m20:_,m21:_,m22:_,m23:_}=self;}
}
#[derive(Copy)]
struct Sl{p19:ZF,p20:ZF,p21:ZF,p22:ZF,p23:ZF}
impl Yr of Destruct<Sl>{
#[inline(always)]
fn destruct(self:Sl) nopanic{let Sl{p19:_,p20:_,p21:_,p22:_,p23:_}=self;}
}
#[derive(Copy)]
struct MK{g0:Uk,g1:Wk,g2:Yk,g3:Pl,g4:Rl,al:Uh}
impl Zr of Destruct<MK>{
#[inline(always)]
fn destruct(self:MK) nopanic{let MK{g0:_,g1:_,g2:_,g3:_,g4:_,al:_}=self;}
}
#[derive(Copy)]
struct PW{g0:Vk,g1:Xk,g2:Zk,g3:Ql,g4:Sl}
impl Ps of Destruct<PW>{
#[inline(always)]
fn destruct(self:PW) nopanic{let PW{g0:_,g1:_,g2:_,g3:_,g4:_}=self;}
}
const Ss:MK=MK{g0:Uk{m0:0x80000000000000008000000000000000},g1:Wk{m1:0xfffffffff0000000fffffffff0000000,m2:0xe000000000000000e000000000000000,m3:0xffffffffff800000ffffffffff800000,m4:0xffffc00000000000ffffc00000000000,m5:0xfffffffffff00000fffffffffff00000,m6:0xffc0000000000000ffc0000000000000},g2:Yk{m7:0xfffffffffff80000fffffffffff80000,m8:0xc000000000000000c000000000000000,m9:0xfffffffffffffffcfffffffffffffffc,m10:0xfc00000000000000fc00000000000000,m11:0xffffffffffe00000ffffffffffe00000,m12:0xfffe000000000000fffe000000000000},g3:Pl{m13:0xfffffffffffffff8fffffffffffffff8,m14:0xfffffff000000000fffffff000000000,m15:0xfffffffffffffe00fffffffffffffe00,m16:0xffffff8000000000ffffff8000000000,m17:0xfffff80000000000fffff80000000000,m18:0xffffffffffffff00ffffffffffffff00},g4:Rl{m19:0xffffffe000000000ffffffe000000000,m20:0xfffff00000000000fffff00000000000,m21:0xfffffffffe000000fffffffffe000000,m22:0xff00000000000000ff00000000000000,m23:0xfffc000000000000fffc000000000000},al:Ze};
const Pz:PW=PW{g0:Vk{p0:2},g1:Xk{p1:68719476736,p2:8,p3:2199023255552,p4:262144,p5:17592186044416,p6:1024},g2:Zk{p7:35184372088832,p8:4,p9:4611686018427387904,p10:64,p11:8796093022208,p12:32768},g3:Ql{p13:2305843009213693952,p14:268435456,p15:36028797018963968,p16:33554432,p17:2097152,p18:72057594037927936},g4:Sl{p19:134217728,p20:1048576,p21:549755813888,p22:256,p23:16384}};
#[inline(always)]
fn tp(s:[u128;25],mk:MK)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=s;
let pw=Pz;
let c0=a0^a5^a10^a15^a20;
let c1=a1^a6^a11^a16^a21;
let c2=a2^a7^a12^a17^a22;
let c3=a3^a8^a13^a18^a23;
let c4=a4^a9^a14^a19^a24;
let d0=c4^rt1(c1,mk.g0.m0);
let d1=c0^rt1(c2,mk.g0.m0);
let d2=c1^rt1(c3,mk.g0.m0);
let d3=c2^rt1(c4,mk.g0.m0);
let d4=c3^rt1(c0,mk.g0.m0);
let e0=a0^d0;
let e1=a1^d1;
let e2=a2^d2;
let e3=a3^d3;
let e4=a4^d4;
let e5=a5^d0;
let e6=a6^d1;
let e7=a7^d2;
let e8=a8^d3;
let e9=a9^d4;
let e10=a10^d0;
let e11=a11^d1;
let e12=a12^d2;
let e13=a13^d3;
let e14=a14^d4;
let e15=a15^d0;
let e16=a16^d1;
let e17=a17^d2;
let e18=a18^d3;
let e19=a19^d4;
let e20=a20^d0;
let e21=a21^d1;
let e22=a22^d2;
let e23=a23^d3;
let e24=a24^d4;
let b0=e0;
let b16=rt(e5,mk.g1.m1,pw.g1.p1,0x80000000000001100000000000000000000000000000001000000000);
let b7=rt(e10,mk.g1.m2,pw.g1.p2,0x400000000000008800000000000000000000000000000008);
let b23=rt(e15,mk.g1.m3,pw.g1.p3,0x1000000000000022000000000000000000000000000000020000000000);
let b14=rt(e20,mk.g1.m4,pw.g1.p4,0x2000000000000044000000000000000000000000000000040000);
let b10=rt1(e1,mk.g0.m0);
let b1=rt(e6,mk.g1.m5,pw.g1.p5,0x8000000000000110000000000000000000000000000000100000000000);
let b17=rt(e11,mk.g1.m6,pw.g1.p6,0x20000000000000440000000000000000000000000000000400);
let b8=rt(e16,mk.g2.m7,pw.g2.p7,0x10000000000000220000000000000000000000000000000200000000000);
let b24=rt(e21,mk.g2.m8,pw.g2.p8,0x200000000000004400000000000000000000000000000004);
let b20=rt(e2,mk.g2.m9,pw.g2.p9,0x200000000000004400000000000000000000000000000004000000000000000);
let b11=rt(e7,mk.g2.m10,pw.g2.p10,0x2000000000000044000000000000000000000000000000040);
let b2=rt(e12,mk.g2.m11,pw.g2.p11,0x4000000000000088000000000000000000000000000000080000000000);
let b18=rt(e17,mk.g2.m12,pw.g2.p12,0x400000000000008800000000000000000000000000000008000);
let b9=rt(e22,mk.g3.m13,pw.g3.p13,0x100000000000002200000000000000000000000000000002000000000000000);
let b5=rt(e3,mk.g3.m14,pw.g3.p14,0x800000000000011000000000000000000000000000000010000000);
let b21=rt(e8,mk.g3.m15,pw.g3.p15,0x4000000000000088000000000000000000000000000000080000000000000);
let b12=rt(e13,mk.g3.m16,pw.g3.p16,0x100000000000002200000000000000000000000000000002000000);
let b3=rt(e18,mk.g3.m17,pw.g3.p17,0x10000000000000220000000000000000000000000000000200000);
let b19=rt(e23,mk.g3.m18,pw.g3.p18,0x8000000000000110000000000000000000000000000000100000000000000);
let b15=rt(e4,mk.g4.m19,pw.g4.p19,0x400000000000008800000000000000000000000000000008000000);
let b6=rt(e9,mk.g4.m20,pw.g4.p20,0x8000000000000110000000000000000000000000000000100000);
let b22=rt(e14,mk.g4.m21,pw.g4.p21,0x400000000000008800000000000000000000000000000008000000000);
let b13=rt(e19,mk.g4.m22,pw.g4.p22,0x8000000000000110000000000000000000000000000000100);
let b4=rt(e24,mk.g4.m23,pw.g4.p23,0x200000000000004400000000000000000000000000000004000);
[b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24]
}
#[inline(always)]
fn jag(s:[u128;25],rc:u128,mk:MK)->[u128;25]{
let[b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24]=tp(s,mk);
let n3=jaa(b3,mk.al);
let a0=b0^(b1&b2)^rc;
let a1=b1^(b2|n3);
let a2=b2^(b3|b4);
let a3=b3^(b4&b0);
let a4=b4^(b0|b1);
let n8=jaa(b8,mk.al);
let a5=b5^(b6&b7);
let a6=b6^(b7|n8);
let a7=b7^(b8|b9);
let a8=b8^(b9&b5);
let a9=b9^(b5|b6);
let ia=jaa(b12,mk.al);
let a10=b10^(b11|ia);
let a11=b11^(b12|b13);
let a12=ia^(b13&b14);
let a13=b13^(b14|b10);
let a14=b14^(b10&b11);
let n18=jaa(b18,mk.al);
let a15=b15^(b16|b17);
let a16=b16^(b17&b18);
let a17=b17^(n18&b19);
let a18=n18^(b19|b15);
let a19=b19^(b15&b16);
let n23=jaa(b23,mk.al);
let a20=b20^(b21&b22);
let a21=b21^(b22|n23);
let a22=b22^(b23|b24);
let a23=b23^(b24&b20);
let a24=b24^(b20|b21);
[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]
fn kag(s:[u128;25],rc:u128,mk:MK)->[u128;25]{
let[b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24]=tp(s,mk);
let n1=jaa(b1,mk.al);
let a0=b0^(b1&b2)^rc;
let a1=b1^(b2|b3);
let a2=b2^(b3&b4);
let a3=b3^(b4|b0);
let a4=b4^(b0&n1);
let n7=jaa(b7,mk.al);
let a5=b5^(b6|b7);
let a6=b6^(n7|b8);
let a7=b7^(b8&b9);
let a8=b8^(b9|b5);
let a9=b9^(b5&b6);
let ia=jaa(b14,mk.al);
let a10=b10^(b11|b12);
let a11=b11^(b12&b13);
let a12=b12^(b13|b14);
let a13=b13^(ia|b10);
let a14=ia^(b10&b11);
let n18=jaa(b18,mk.al);
let a15=b15^(b16&b17);
let a16=b16^(b17|n18);
let a17=b17^(b18|b19);
let a18=b18^(b19&b15);
let a19=b19^(b15|b16);
let n23=jaa(b23,mk.al);
let a20=b20^(b21&b22);
let a21=b21^(b22|b23);
let a22=b22^(n23|b24);
let a23=n23^(b24&b20);
let a24=b24^(b20|b21);
[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]
fn lag(s:[u128;25],rc:u128,mk:MK)->[u128;25]{
let[b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24]=tp(s,mk);
let n4=jaa(b4,mk.al);
let a0=b0^(b1&b2)^rc;
let a1=b1^(b2|b3);
let a2=b2^(b3&b4);
let a3=b3^(n4&b0);
let a4=n4^(b0|b1);
let n5=jaa(b5,mk.al);
let a5=n5^(b6|b7);
let a6=b6^(b7&b8);
let a7=b7^(b8|b9);
let a8=b8^(b9&n5);
let a9=b9^(b5&b6);
let oa=jaa(b13,mk.al);
let a10=b10^(b11&b12);
let a11=b11^(b12|oa);
let a12=b12^(b13|b14);
let a13=b13^(b14&b10);
let a14=b14^(b10|b11);
let ib=jaa(b19,mk.al);
let a15=b15^(b16&b17);
let a16=b16^(b17|b18);
let a17=b17^(b18&ib);
let a18=b18^(b19&b15);
let a19=b19^(b15|b16);
let ia=jaa(b20,mk.al);
let a20=ia^(b21&b22);
let a21=b21^(b22|b23);
let a22=b22^(b23&b24);
let a23=b23^(b24|ia);
let a24=b24^(b20|b21);
[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]
fn mag(s:[u128;25],rc:u128,mk:MK)->[u128;25]{
let[b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24]=tp(s,mk);
let n1=jaa(b1,mk.al);
let a0=b0^(n1|b2)^rc;
let a1=n1^(b2&b3);
let a2=b2^(b3|b4);
let a3=b3^(b4&b0);
let a4=b4^(b0|b1);
let n9=jaa(b9,mk.al);
let a5=b5^(b6&b7);
let a6=b6^(b7|b8);
let a7=b7^(b8&b9);
let a8=b8^(n9&b5);
let a9=n9^(b5|b6);
let n10=jaa(b10,mk.al);
let a10=b10^(b11|b12);
let a11=b11^(b12&b13);
let a12=b12^(b13|b14);
let a13=b13^(b14&n10);
let a14=b14^(b10&b11);
let n17=jaa(b17,mk.al);
let a15=b15^(b16&n17);
let a16=b16^(b17&b18);
let a17=b17^(b18|b19);
let a18=b18^(b19&b15);
let a19=b19^(b15|b16);
let n23=jaa(b23,mk.al);
let a20=b20^(b21&b22);
let a21=b21^(b22|n23);
let a22=b22^(b23|b24);
let a23=b23^(b24&b20);
let a24=b24^(b20|b21);
[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]fn zai(s:[u128;25],sel:ZF)->[u128;25]{
let all:Uh=Ze;
let mk=Ss;
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=s;
let c0=a0^a5^a10^a15^a20;
let c1=a1^a6^a11^a16^a21;
let c2=a2^a7^a12^a17^a22;
let c3=a3^a8^a13^a18^a23;
let c4=a4^a9^a14^a19^a24;
let d0=c4^rt1(c1,mk.g0.m0);
let d1=c0^rt1(c2,mk.g0.m0);
let d2=c1^rt1(c3,mk.g0.m0);
let d3=c2^rt1(c4,mk.g0.m0);
let d4=c3^rt1(c0,mk.g0.m0);
let b0=a0^d0;
let b1=rt(a6^d1,mk.g1.m5,17592186044416,0);
let b2=rt(a12^d2,mk.g2.m11,8796093022208,0);
let b3=rt(a18^d3,mk.g3.m17,2097152,0);
let b4=rt(a24^d4,mk.g4.m23,16384,0);
let b5=rt(a3^d3,mk.g3.m14,268435456,0);
let b6=rt(a9^d4,mk.g4.m20,1048576,0);
let b7=rt(a10^d0,mk.g1.m2,8,0);
let b8=rt(a16^d1,mk.g2.m7,35184372088832,0);
let b9=rt(a22^d2,mk.g3.m13,2305843009213693952,0);
let rc:u128=0x7fffffff7fff7ff77fffffff7fff7ff7;
let n1=jaa(b1,all);
let y1=a1;let y7=a7;
let x0=b0^(n1|b2)^rc;
let x1=n1^(b2&b3);
let x2=b2^(b3|b4);
let x3=b3^(b4&b0);
let x4=b4^(b0|b1);
let a5=b5^(b6&b7);
let a6=b6^(b7|b8);
let a7=b7^(b8&b9);
if sel!=0{
return [x0,x1,x2,x3,x4,a5,a6,a7,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
}
let n9=jaa(b9,all);
let a8=b8^(n9&b5);
let a9=n9^(b5|b6);
let b10=rt1(y1^d1,mk.g0.m0);
let b11=rt(y7^d2,mk.g2.m10,64,0);
let b12=rt(a13^d3,mk.g3.m16,33554432,0);
let b13=rt(a19^d4,mk.g4.m22,256,0);
let b14=rt(a20^d0,mk.g1.m4,262144,0);
let n10=jaa(b10,all);
let a10=b10^(b11|b12);
let a11=b11^(b12&b13);
let a12=b12^(b13|b14);
let a13=b13^(b14&n10);
let a14=b14^(b10&b11);
[x0,x1,x2,x3,x4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,KG,0xffffffffffffffff,KG,KG,KG,KG,0,0,0,0]
}
fn zah(st:[u128;25],g:Box<[u128;13]>,mk:MK,h:Nullable<[u128;13]>)->[u128;25]{
let[r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,_]=g.unbox();
let mut st=jag(st,r0,mk);
st=kag(st,r1,mk);
st=lag(st,r2,mk);
st=mag(st,r3,mk);
st=jag(st,r4,mk);
st=kag(st,r5,mk);
st=lag(st,r6,mk);
st=mag(st,r7,mk);
st=jag(st,r8,mk);
st=kag(st,r9,mk);
st=lag(st,r10,mk);
match Into::<u128,ZF>::into(r11){0=>{let[_,_,_,_,_,_,_,_,_,_,_,_,sel]=g.unbox();let sel:ZF=sel.into();if sel==1{return st;}return zai(st,sel);},_=>{},}
st=mag(st,r11,mk);
match core::nullable::match_nullable(h){core::nullable::FromNullableResult::Null=>st,core::nullable::FromNullableResult::NotNull(b)=>zah(st,b,mk,core::nullable::null()),}
}
#[inline(always)]
fn raa(s:[u128;25],rcs:(Box<[u128;13]>,Nullable<[u128;13]>))->[u128;25]{
let(g,h)=rcs;
zah(s,g,Ss,h)
}
pub const Zj:[u128;24]=[0x10000000000000001,0x80820000000000008082,0x800000000000808a800000000000808a,0x7fffffff7fff7fff7fffffff7fff7fff,0x808b000000000000808b,0x800000010000000080000001,0x80000000800080818000000080008081,0x7fffffffffff7ff67fffffffffff7ff6,0x8a000000000000008a,0x880000000000000088,0x800080090000000080008009,0xffffffff7ffffff5ffffffff7ffffff5,0x8000808b000000008000808b,0x800000000000008b800000000000008b,0x80000000000080898000000000008089,0x7fffffffffff7ffc7fffffffffff7ffc,0x80000000000080028000000000008002,0x80000000000000808000000000000080,0x800a000000000000800a,0x7fffffff7ffffff57fffffff7ffffff5,0x80000000800080818000000080008081,0x80000000000080808000000000008080,0x800000010000000080000001,0x7fffffff7fff7ff77fffffff7fff7ff7];
pub const KG:u128=0xffffffffffffffff0000000000000000;
use corelib_imports::bounded_int::{AddHelper,MulHelper,UnitInt as ZU};
mod shh{
pub impl A<L,R,const LO:felt252,const HI:felt252>of super::AddHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
pub impl M<L,R,const LO:felt252,const HI:felt252>of super::MulHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
}
#[inline(always)]
fn mac<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::add::<L,R,shh::A<L,R,LO,HI>>(l,r)
}
#[inline(always)]
fn aab<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::mul::<L,R,shh::M<L,R,LO,HI>>(l,r)
}
pub(crate) type Ln=ZB<0x1f000100000000001f0000,0x1f030300000000001f0302>;
pub(crate) type Lm=ZB<0x100000000001f000000000000001f00,0x300000000001f030200000000001f03>;
#[inline(always)]
pub fn lad(a0:u128,a1:u128,a2:u128,a3:u128)->[u128;25]{
let all:Uh=Ze;
let c0=a0^0x80000000000000008000000000000000;
let d1=c0^rt1(a2,0x80000000000000008000000000000000);
let d2=a1^rt1(a3,0x80000000000000008000000000000000);
let d4=a3^rt1(c0,0x80000000000000008000000000000000);
let ia=rt1(a1,0x80000000000000008000000000000000);
let e1=a1^d1;let e2=a2^d2;let x20=ia^0x80000000000000008000000000000000;let e3=a3^a2;
let b0=a0^ia;
let b16=rt(ia,0xfffffffff0000000fffffffff0000000,68719476736,0);
let b7=rt(ia,0xe000000000000000e000000000000000,8,0);
let b23=rt(ia,0xffffffffff800000ffffffffff800000,2199023255552,0);
let b14=rt(x20,0xffffc00000000000ffffc00000000000,262144,0);
let b10=rt1(e1,0x80000000000000008000000000000000);
let b1=rt(d1,0xfffffffffff00000fffffffffff00000,17592186044416,0);
let b17=rt(d1,0xffc0000000000000ffc0000000000000,1024,0);
let b8=rt(d1,0xfffffffffff80000fffffffffff80000,35184372088832,0);
let b24=rt(d1,0xc000000000000000c000000000000000,4,0);
let b20=rt(e2,0xfffffffffffffffcfffffffffffffffc,4611686018427387904,0);
let b11=rt(d2,0xfc00000000000000fc00000000000000,64,0);
let b2=rt(d2,0xffffffffffe00000ffffffffffe00000,8796093022208,0);
let b18=rt(d2,0xfffe000000000000fffe000000000000,32768,0);
let b9=rt(d2,0xfffffffffffffff8fffffffffffffff8,2305843009213693952,0);
let b5=rt(e3,0xfffffff000000000fffffff000000000,268435456,0);
let b21=rt(a2,0xfffffffffffffe00fffffffffffffe00,36028797018963968,0);
let b12=rt(a2,0xffffff8000000000ffffff8000000000,33554432,0);
let b3=rt(a2,0xfffff80000000000fffff80000000000,2097152,0);
let b19=rt(a2,0xffffffffffffff00ffffffffffffff00,72057594037927936,0);
let b15=rt(d4,0xffffffe000000000ffffffe000000000,134217728,0);
let b6=rt(d4,0xfffff00000000000fffff00000000000,1048576,0);
let b22=rt(d4,0xfffffffffe000000fffffffffe000000,549755813888,0);
let b13=rt(d4,0xff00000000000000ff00000000000000,256,0);
let b4=rt(d4,0xfffc000000000000fffc000000000000,16384,0);
[b0,b1,b2,b3,jaa(b4,all),b5,jaa(b6,all),b7,jaa(b8,all),b9,b10,b11,jaa(b12,all),b13,jaa(b14,all),b15,jaa(b16,all),b17,b18,jaa(b19,all),b20,jaa(b21,all),b22,b23,jaa(b24,all)]
}
#[inline(always)]
pub fn aaj(h:[u128;25],all:Uh)->(u128,u128,u128,u128,u128){
let[_,h1,h2,_,_,_,_,_,h8,h9,h10,h11,_,_,_,_,_,h17,h18,_,h20,_,_,_,h24]=h;
((jaa(h1,all)&h2)^0x10000000000000001,h8&h9,jaa(h10,all)&h11,jaa(h17,all)&h18,h24&h20)
}
#[inline(always)]
pub(crate) fn jab(h:[u128;25],kx:(u128,u128,u128,u128,u128),p:(Ln,Lm),all:Uh,g1y:Box<[u128;13]>)->[u128;25]{
let(k0,k7,k14,k16,oa)=kx;
let[h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24]=h;
let(ia,lb)=p;
let l0:u128=zu(ia);
let l3:u128=zu(aab::<_,_,0x7c000400000000007c000000000,0x7c0c0c00000000007c0c0800000>(ia,Ww));
let l5:u128=zu(aab::<_,_,0x3e000200000000003e00000000000,0x3e060600000000003e06040000000>(ia,Xw));
let l7:u128=zu(aab::<_,_,0xf800080000000000f80000,0xf818180000000000f81810>(ia,Tz));
let l12:u128=zu(aab::<_,_,0x7c000400000000007c0000000000,0x7c0c0c00000000007c0c08000000>(ia,Yw));
let l14:u128=zu(aab::<_,_,0x7c000400000000007c00000000,0x7c0c0c00000000007c0c080000>(ia,Zw));
let l15:u128=zu(aab::<_,_,0xf800080000000000f80000000000,0xf818180000000000f81810000000>(ia,Px));
let l16:u128=zu(aab::<_,_,0x1f000100000000001f0000000000000,0x1f030300000000001f0302000000000>(ia,Qx));
let l19:u128=zu(aab::<_,_,0x200000000003e000000000000003e00,0x600000000003e060400000000003e06>(lb,U2));
let l21:u128=zu(lb);
let l23:u128=zu(aab::<_,_,0x3e000200000000003e00000000000000,0x3e060600000000003e06040000000000>(ia,Xx));
let b0=h0^l0;
let b1=h1;
let b2=h2;
let b3=h3^l3;
let b4=h4;
let b5=h5^l5;
let b6=h6;
let b7=h7^l7;
let b8=h8;
let b9=h9;
let b10=h10;
let b11=h11;
let b12=h12^l12;
let b13=h13;
let b14=h14^l14;
let b15=h15^l15;
let b16=h16^l16;
let b17=h17;
let b18=h18;
let b19=h19^l19;
let b20=h20;
let b21=h21^l21;
let b22=h22;
let b23=h23^l23;
let b24=h24;
let n1=jaa(b1,all);
let n2=jaa(b2,all);
let n9=jaa(b9,all);
let n10=jaa(b10,all);
let n17=jaa(b17,all);
let n23=jaa(b23,all);
let a0=b0^k0;
let a1=b1^(n2&b3);
let a2=n2^(b3|b4);
let a3=b3^(b4&b0);
let a4=b4^(b0|n1);
let a5=b5^(b6&b7);
let a6=b6^(b7|b8);
let a7=b7^k7;
let a8=b8^(n9&b5);
let a9=n9^(b5|b6);
let a10=n10^(b11|b12);
let a11=b11^(b12&b13);
let a12=b12^(b13|b14);
let a13=b13^(b14&b10);
let a14=b14^k14;
let a15=b15^(b16&b17);
let a16=b16^k16;
let a17=n17^(b18|b19);
let a18=b18^(b19&b15);
let a19=b19^(b15|b16);
let a20=b20^(b21&b22);
let a21=b21^(b22|n23);
let a22=b22^(b23|b24);
let a23=b23^oa;
let a24=b24^(b20|b21);
let st=[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24];
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=raa(st,(g1y,hfull_y()));
[a0,a1,a2,jaa(a3,all),a4,jaa(a5,all),a6,a7,jaa(a8,all),jaa(a9,all),a10,a11,jaa(a12,all),a13,jaa(a14,all),a15,jaa(a16,all),a17,jaa(a18,all),a19,jaa(a20,all),a21,jaa(a22,all),a23,jaa(a24,all)]
}
pub(crate) const Yx:[u128;24]=[0x80820000000000008082,0x800000000000808a800000000000808a,0x80000000800080008000000080008000,0xffffffffffff7f74ffffffffffff7f74,0x800000010000000080000001,0x80000000800080818000000080008081,0x80000000000080098000000000008009,0xffffffffffffff75ffffffffffffff75,0x880000000000000088,0x800080090000000080008009,0x8000000a000000008000000a,0xffffffff7fff7f74ffffffff7fff7f74,0x800000000000008b800000000000008b,0x80000000000080898000000000008089,0x80000000000080038000000000008003,0x7fffffffffff7ffd7fffffffffff7ffd,0x80000000000000808000000000000080,0x800a000000000000800a,0x800000008000000a800000008000000a,0x7fffffff7fff7f7e7fffffff7fff7f7e,0x80000000000080808000000000008080,0x800000010000000080000001,0x80000000800080088000000080008008,0x0];
const U2:ZU<0x2>=0x2;
const Zw:ZU<0x40000>=0x40000;
const Ww:ZU<0x400000>=0x400000;
const Yw:ZU<0x4000000>=0x4000000;
const Px:ZU<0x8000000>=0x8000000;
const Xw:ZU<0x20000000>=0x20000000;
const Tz:ZU<0x8>=0x8;
const Qx:ZU<0x1000000000>=0x1000000000;
const Xx:ZU<0x20000000000>=0x20000000000;
pub trait Ap<T>{fn p(ref self:Array<T>,v:T);}
pub impl PL<T> of Ap<T>{#[inline(always)]fn p(ref self:Array<T>,v:T){self.append(v)}}
type ZF=felt252;
