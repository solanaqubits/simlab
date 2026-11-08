use crate::k2::Ap;
use corelib_imports::bounded_int::{AddHelper,BoundedInt as ZB,DivRemHelper as ZD,MulHelper,UnitInt as ZU,bounded_int as zq,upcast as zu};
use crate::k2::{keccak_f1600_x2,naa,nt,kab,hab,lab,rcs};
use crate::sa0::{Za,keep};
type U64=ZB<0,0xffffffffffffffff>;
impl SN of ZD<u128,ZU<0x10000000000000000>>{
type DivT=U64;
type RemT=U64;
}
const Wg:NonZero<ZU<0x10000000000000000>>=0x10000000000000000;
impl Qn of core::internal::bounded_int::ConstrainHelper<ZB<0,0x7fffffffffffffffff>,0x800000>{type LowT=ZB<0,0x7fffff>;type HighT=ZB<0x800000,0x7fffffffffffffffff>;}
impl TC of core::internal::bounded_int::ConstrainHelper<u128,0x8000000000000000000000>{type LowT=ZB<0,0x7fffffffffffffffffffff>;type HighT=ZB<0x8000000000000000000000,0xffffffffffffffffffffffffffffffff>;}
impl UC of core::internal::bounded_int::ConstrainHelper<ZB<0,0x7fffffffffffffffffffff>,0x800000000000000000>{type LowT=ZB<0,0x7fffffffffffffffff>;type HighT=ZB<0x800000000000000000,0x7fffffffffffffffffffff>;}
impl QK of core::internal::bounded_int::ConstrainHelper<u128,0x800000000000000000>{type LowT=ZB<0,0x7fffffffffffffffff>;type HighT=ZB<0x800000000000000000,0xffffffffffffffffffffffffffffffff>;}
impl TN of ZD<u128,ZU<0x800000000000000000>>{type DivT=ZB<0,0x1ffffffffffffff>;type RemT=ZB<0,0x7fffffffffffffffff>;}
const Ut:NonZero<ZU<0x800000000000000000>>=0x800000000000000000;
use core::internal::bounded_int::constrain;
const HI:u128=0x10000000000000000;
const LO:u128=0xffffffffffffffff;
#[inline(always)]
pub(crate)fn qai(w:u128)->(u128,u128){
let(h,l)=zq::div_rem(w,Wg);
(zu(l),zu(h))
}
const VC:u128=0xffff7fffff7fffffffff7fffff7fffff;
const WC:u128=0xff7fffff7fffff7fff7fffff7fffff7f;
const XC:u128=0x7fffff7fffff7fff7fffff7fffff7fff;
const H0:u128=0xffff7fffff7fffff0000000000000000;
const H1:u128=0xff7fffff7fffff7f0000000000000000;
const H2:u128=0x7fffff7fffff7fff0000000000000000;
const K0:u128=0x1fff001fff0000001fff001fff;
const K1:u128=0x1fff001fff0100001fff001fff01;
const K2:u128=0x1fff001fff0020001fff001fff0020;
const T0:u128=0x8000008000000000800000800000;
const T1:u128=0x800000800000800080000080000080;
const T2:u128=0x80000080000080008000008000008000;
const Pp:u128=0x1fff001fff0000000000000000;
const Qp:u128=0x1fff001fff010000000000000000;
const Rp:u128=0x1fff001fff00200000000000000000;
const Sp:u128=0x8000008000000000000000000000;
const Tp:u128=0x800000800000800000000000000000;
const Up:u128=0x80000080000080000000000000000000;
const T5:u128=0x800000800000800000800000800000;
mod th{
pub impl D<L,R,const QH:felt252,const RH:felt252>of super::ZD<L,R>{type DivT=super::ZB<0,QH>;type RemT=super::ZB<0,RH>;}
pub impl A<L,R,const LO:felt252,const HI:felt252>of super::AddHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
pub impl M<L,R,const LO:felt252,const HI:felt252>of super::MulHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
}
#[inline(always)]
fn gaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::add::<L,R,th::A<L,R,LO,HI>>(l,r)
}
#[inline(always)]
fn kaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::mul::<L,R,th::M<L,R,LO,HI>>(l,r)
}
impl SK of ZD<U64,ZU<0x1000000>>{type DivT=ZB<0,0xffffffffff>;type RemT=Za;}
impl TK of ZD<ZB<0,0xffffffffff>,ZU<0x1000000>>{type DivT=ZB<0,0xffff>;type RemT=Za;}
impl UN of ZD<U64,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffff>;type RemT=ZB<0,0xff>;}
impl UK of ZD<ZB<0,0xffffffffffffff>,ZU<0x1000000>>{type DivT=ZB<0,0xffffffff>;type RemT=Za;}
impl VK of ZD<ZB<0,0xffffffff>,ZU<0x1000000>>{type DivT=ZB<0,0xff>;type RemT=Za;}
impl WK of ZD<U64,ZU<0x10000>>{type DivT=ZB<0,0xffffffffffff>;type RemT=ZB<0,0xffff>;}
impl XK of ZD<ZB<0,0xffffffffffff>,ZU<0x1000000>>{type DivT=Za;type RemT=Za;}
const Qk:NonZero<ZU<0x1000000>>=0x1000000;
const N8:NonZero<ZU<0x100>>=0x100;
const Yf:NonZero<ZU<0x10000>>=0x10000;
const U16:ZU<0x10000>=0x10000;
const U8:ZU<0x100>=0x100;
const Vp:ZU<0x10000000000000000>=0x10000000000000000;
#[inline(always)]
fn aaa<L,R,const QH:felt252,const RH:felt252>(l:L,r:NonZero<R>)->(ZB<0,QH>,ZB<0,RH>){zq::div_rem::<L,R,th::D<L,R,QH,RH>>(l,r)}
#[inline(always)]
pub(crate)fn maa(w:u128,n64:NonZero<ZU<0x10000000000000000>>)->(U64,U64){
let(h,l)=zq::div_rem(w,n64);
(l,h)
}
#[inline(always)]
fn uaa(l0:U64,l1:U64,l2:U64,n24:NonZero<ZU<0x1000000>>,n8:NonZero<ZU<0x100>>,n16:NonZero<ZU<0x10000>>)->(Za,Za,Za,Za,Za,Za,Za,Za){
let(x,c0)=zq::div_rem(l0,n24);
let(c2_low,c1)=zq::div_rem(x,n24);
let(x,c2_high)=zq::div_rem(l1,n8);
let(x,c3)=zq::div_rem(x,n24);
let(c5_low,c4)=zq::div_rem(x,n24);
let(x,c5_high)=zq::div_rem(l2,n16);
let(c7,c6)=zq::div_rem(x,n24);
let c2:Za=gaa::<_,_,0,16777215>(c2_low,kaa::<_,_,0,16711680>(c2_high,U16));
let c5:Za=gaa::<_,_,0,16777215>(c5_low,kaa::<_,_,0,16776960>(c5_high,U8));
(c0,c1,c2,c3,c4,c5,c6,c7)
}
#[inline(always)]
fn pt5(c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,t5:u128)->ZF{
const Ra:ZU<16777216>=16777216;
const Sa:ZU<281474976710656>=281474976710656;
const Ta:ZU<4722366482869645213696>=4722366482869645213696;
const Ua:ZU<79228162514264337593543950336>=79228162514264337593543950336;
const Va:ZU<648957917835245355975654101753855>=648957917835245355975654101753855;
let acc=c0;
let t=kaa::<_,_,0,281474959933440>(c1,Ra);
let acc=gaa::<_,_,0,281474976710655>(acc,t);
let t=kaa::<_,_,0,4722366201394668503040>(c2,Sa);
let acc=gaa::<_,_,0,4722366482869645213695>(acc,t);
let t=kaa::<_,_,0,79228157791897854723898736640>(c3,Ta);
let acc=gaa::<_,_,0,79228162514264337593543950335>(acc,t);
let t=kaa::<_,_,0,1329227916556753358639469466736394240>(c4,Ua);
let acc=gaa::<_,_,0,1329227995784915872903807060280344575>(acc,t);
let acc=gaa::<_,_,648957917835245355975654101753855,1329876953702751118259782714382098430>(acc,Va);
let p:u128=zu(acc);
(p&t5).into()
}
#[inline(always)]
fn pt4(c0:Za,c1:Za,c2:Za,c3:Za,t5:u128)->ZF{
const Ra:ZU<16777216>=16777216;
const Sa:ZU<281474976710656>=281474976710656;
const Ta:ZU<4722366482869645213696>=4722366482869645213696;
const Va:ZU<648957917835245355975654101753855>=648957917835245355975654101753855;
let acc=c0;
let t=kaa::<_,_,0,281474959933440>(c1,Ra);
let acc=gaa::<_,_,0,281474976710655>(acc,t);
let t=kaa::<_,_,0,4722366201394668503040>(c2,Sa);
let acc=gaa::<_,_,0,4722366482869645213695>(acc,t);
let t=kaa::<_,_,0,79228157791897854723898736640>(c3,Ta);
let acc=gaa::<_,_,0,79228162514264337593543950335>(acc,t);
let acc=gaa::<_,_,648957917835245355975654101753855,649037145997759620313247645704190>(acc,Va);
let p:u128=zu(acc);
(p&t5).into()
}
#[inline(always)]
fn wt(w:u128,k:u128,t:u128)->ZF{
let x:u128=(Into::<u128,ZF>::into(w)+k.into()).try_into().unwrap();
(x&t).into()
}
#[inline(always)]
fn yai()->Za{
0
}

#[inline(never)]
fn cab(c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,c8:Za,c9:Za,c10:Za,c11:Za,c12:Za,c13:Za,c14:Za,c15:Za,ref a:Array<Za>){
keep(c0,ref a);keep(c1,ref a);keep(c2,ref a);keep(c3,ref a);keep(c4,ref a);keep(c5,ref a);keep(c6,ref a);keep(c7,ref a);keep(c8,ref a);keep(c9,ref a);keep(c10,ref a);keep(c11,ref a);keep(c12,ref a);keep(c13,ref a);keep(c14,ref a);keep(c15,ref a);
}
#[inline(never)]
fn rad(c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,ref a:Array<Za>){
keep(c0,ref a);keep(c1,ref a);keep(c2,ref a);keep(c3,ref a);keep(c4,ref a);keep(c5,ref a);keep(c6,ref a);keep(c7,ref a);
}
#[inline(always)]
fn vaa(ref a:Array<Za>,c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,c8:Za,c9:Za,c10:Za,c11:Za,c12:Za,c13:Za,c14:Za,c15:Za){
a.p(c0);a.p(c1);a.p(c2);a.p(c3);a.p(c4);a.p(c5);a.p(c6);a.p(c7);a.p(c8);a.p(c9);a.p(c10);a.p(c11);a.p(c12);a.p(c13);a.p(c14);a.p(c15);
}
#[inline(always)]
fn oac(ref a:Array<Za>,c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za){
a.p(c0);a.p(c1);a.p(c2);a.p(c3);a.p(c4);a.p(c5);a.p(c6);a.p(c7);
}
#[inline(always)]
fn af(r:ZF)->ZF{
let v:u256=r.into();
let(_,l)=zq::div_rem(v.low,Ut);
zu(l)
}
#[inline(always)]
fn bcl(r:ZF)->bool{
core::internal::bounded_int::downcast::<ZF,ZB<0,0x7fffffffffffffffff>>(r).is_some()
}
#[inline(always)]
fn fac(
ref a:Array<Za>,
c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,
c8:Za,c9:Za,c10:Za,c11:Za,c12:Za,c13:Za,c14:Za,c15:Za,
c16:Za,c17:Za,c18:Za,c19:Za,c20:Za,c21:Za,c22:Za,c23:Za,
c24:Za,c25:Za,c26:Za,c27:Za,c28:Za,c29:Za,c30:Za,c31:Za,
){
a.p(c0);a.p(c1);a.p(c2);a.p(c3);a.p(c4);a.p(c5);a.p(c6);a.p(c7);
a.p(c8);a.p(c9);a.p(c10);a.p(c11);a.p(c12);a.p(c13);a.p(c14);a.p(c15);
a.p(c16);a.p(c17);a.p(c18);a.p(c19);a.p(c20);a.p(c21);a.p(c22);a.p(c23);
a.p(c24);a.p(c25);a.p(c26);a.p(c27);a.p(c28);a.p(c29);a.p(c30);a.p(c31);
}
#[inline(always)]
fn gac(
ref a:Array<Za>,
c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,
c8:Za,c9:Za,c10:Za,c11:Za,c12:Za,c13:Za,c14:Za,c15:Za,
c16:Za,c17:Za,c18:Za,c19:Za,c20:Za,c21:Za,c22:Za,c23:Za,
c24:Za,c25:Za,c26:Za,c27:Za,c28:Za,c29:Za,c30:Za,c31:Za,
c32:Za,c33:Za,c34:Za,c35:Za,c36:Za,c37:Za,c38:Za,c39:Za,
){
a.p(c0);a.p(c1);a.p(c2);a.p(c3);a.p(c4);a.p(c5);a.p(c6);a.p(c7);
a.p(c8);a.p(c9);a.p(c10);a.p(c11);a.p(c12);a.p(c13);a.p(c14);a.p(c15);
a.p(c16);a.p(c17);a.p(c18);a.p(c19);a.p(c20);a.p(c21);a.p(c22);a.p(c23);
a.p(c24);a.p(c25);a.p(c26);a.p(c27);a.p(c28);a.p(c29);a.p(c30);a.p(c31);
a.p(c32);a.p(c33);a.p(c34);a.p(c35);a.p(c36);a.p(c37);a.p(c38);a.p(c39);
}
#[inline(always)]
fn nab(
ref a:Array<Za>,
c0:Za,c1:Za,c2:Za,c3:Za,c4:Za,c5:Za,c6:Za,c7:Za,
c8:Za,c9:Za,c10:Za,c11:Za,c12:Za,c13:Za,c14:Za,c15:Za,
c16:Za,c17:Za,c18:Za,c19:Za,c20:Za,c21:Za,c22:Za,c23:Za,
c24:Za,c25:Za,c26:Za,c27:Za,c28:Za,c29:Za,c30:Za,c31:Za,
c32:Za,c33:Za,c34:Za,c35:Za,c36:Za,c37:Za,c38:Za,c39:Za,
ia:Za,oa:Za,ib:Za,ob:Za,ic:Za,oc:Za,od:Za,ie:Za,
oe:Za,ag:Za,bg:Za,cg:Za,dg:Za,eg:Za,fg:Za,gg:Za,
){
a.p(c0);a.p(c1);a.p(c2);a.p(c3);a.p(c4);a.p(c5);a.p(c6);a.p(c7);
a.p(c8);a.p(c9);a.p(c10);a.p(c11);a.p(c12);a.p(c13);a.p(c14);a.p(c15);
a.p(c16);a.p(c17);a.p(c18);a.p(c19);a.p(c20);a.p(c21);a.p(c22);a.p(c23);
a.p(c24);a.p(c25);a.p(c26);a.p(c27);a.p(c28);a.p(c29);a.p(c30);a.p(c31);
a.p(c32);a.p(c33);a.p(c34);a.p(c35);a.p(c36);a.p(c37);a.p(c38);a.p(c39);
a.p(ia);a.p(oa);a.p(ib);a.p(ob);a.p(ic);a.p(oc);a.p(od);a.p(ie);
a.p(oe);a.p(ag);a.p(bg);a.p(cg);a.p(dg);a.p(eg);a.p(fg);a.p(gg);
}
#[inline(never)]
#[derive(Copy,Drop)]
struct RK{a:NonZero<ZU<0x10000000000000000>>,b:NonZero<ZU<0x1000000>>,c:NonZero<ZU<0x100>>,d:NonZero<ZU<0x10000>>,f0:u128,f1:u128,f2:u128,f3:u128,f4:u128,f5:u128,f6:u128,f7:u128,f8:u128}
pub(crate)fn aac(h:[u128;25],kx:(u128,u128,u128,u128,u128),p:(crate::k2::Ln,crate::k2::Lm),all:crate::k2::Zl,g1:Box<[u128;13]>,g1y:Box<[u128;13]>)->(Span<Za>,Span<Za>){
let mut st=crate::k2::jab(h,kx,p,all,g1y);
let mut a:Array<Za>=array![];
let mut b:Array<Za>=array![];
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let n24:NonZero<ZU<0x1000000>>=Qk;
let n8:NonZero<ZU<0x100>>=N8;
let n16:NonZero<ZU<0x10000>>=Yf;
let mk0:u128=VC;let mk1:u128=WC;let mk2:u128=XC;let k0:u128=K0;let k1:u128=K1;let k2:u128=K2;let t0:u128=T0;let t1:u128=T1;let t2:u128=T2;
let kg=RK{a:n64,b:n24,c:n8,d:n16,f0:mk0,f1:mk1,f2:mk2,f3:k0,f4:k1,f5:k2,f6:t0,f7:t1,f8:t2};
loop{let RK{a:n64,b:n24,c:n8,d:n16,f0:lg,f1:mg,f2:ng,f3:og,f4:pg,f5:qg,f6:rg,f7:tg,f8:ug}=kg;let mk0=lg;let mk1=mg;let mk2=ng;let k0=og;let k1=pg;let k2=qg;let t0=rg;let t1=tg;let t2=ug;
let[w0,w1,w2,w3,w4,w5,w6,w7,w8,w9,w10,w11,w12,w13,w14,w15,w16,w17,w18,w19,w20,_,_,_,_]=crate::k2::rda(st,all);
let w0=w0&mk0;let w1=w1&mk1;let w2=w2&mk2;
let w3=w3&mk0;let w4=w4&mk1;let w5=w5&mk2;
let w6=w6&mk0;let w7=w7&mk1;let w8=w8&mk2;
let w9=w9&mk0;let w10=w10&mk1;let w11=w11&mk2;
let bq=wt(w0,k0,t0)+wt(w1,k1,t1)+wt(w2,k2,t2)+wt(w3,k0,t0)+wt(w4,k1,t1)+wt(w5,k2,t2);
let ia=bq+wt(w6,k0,t0)+wt(w7,k1,t1)+wt(w8,k2,t2)+wt(w9,k0,t0)+wt(w10,k1,t1)+wt(w11,k2,t2);
let(x0,y0)=maa(w0,n64);let(x1,y1)=maa(w1,n64);let(x2,y2)=maa(w2,n64);
let(x3,y3)=maa(w3,n64);let(x4,y4)=maa(w4,n64);let(x5,y5)=maa(w5,n64);
let(x6,y6)=maa(w6,n64);let(x7,y7)=maa(w7,n64);let(x8,y8)=maa(w8,n64);
let(x9,y9)=maa(w9,n64);let(x10,y10)=maa(w10,n64);let(x11,y11)=maa(w11,n64);
let(a0,a1,a2,a3,a4,a5,a6,a7)=uaa(x0,x1,x2,n24,n8,n16);
let(a8,a9,a10,a11,a12,a13,a14,a15)=uaa(x3,x4,x5,n24,n8,n16);
let(a16,a17,a18,a19,a20,a21,a22,a23)=uaa(x6,x7,x8,n24,n8,n16);
let(a24,a25,a26,a27,a28,a29,a30,a31)=uaa(x9,x10,x11,n24,n8,n16);
let(b0,b1,b2,b3,b4,b5,b6,b7)=uaa(y0,y1,y2,n24,n8,n16);
let(b8,b9,b10,b11,b12,b13,b14,b15)=uaa(y3,y4,y5,n24,n8,n16);
let(b16,b17,b18,b19,b20,b21,b22,b23)=uaa(y6,y7,y8,n24,n8,n16);
let(b24,b25,b26,b27,b28,b29,b30,b31)=uaa(y9,y10,y11,n24,n8,n16);
if a.len()>=224&&b.len()>=224&&ia==0{
fac(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31);
fac(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31);
break;
}
let w12=w12&mk0;let w13=w13&mk1;let w14=w14&mk2;
let(x12,y12)=maa(w12,n64);let(x13,y13)=maa(w13,n64);let(x14,y14)=maa(w14,n64);
let(a32,a33,a34,a35,a36,a37,a38,oa)=uaa(x12,x13,x14,n24,n8,n16);
let(b32,b33,b34,b35,b36,b37,b38,b39)=uaa(y12,y13,y14,n24,n8,n16);
let ib=ia+wt(w12,k0,t0)+wt(w13,k1,t1)+wt(w14,k2,t2);
if a.len()>=216{
if b.len()>=216&&ib==0{
gac(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,a32,a33,a34,a35,a36,a37,a38,oa);
gac(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39);
break;
}
core::gas::withdraw_gas().unwrap();
if af(ib)==0{gac(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,a32,a33,a34,a35,a36,a37,a38,oa);}else{
cab(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,ref a);
cab(a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,ref a);
rad(a32,a33,a34,a35,a36,a37,a38,oa,ref a);
}
if bcl(ib){gac(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39);}else{
cab(b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,ref b);
cab(b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,ref b);
rad(b32,b33,b34,b35,b36,b37,b38,b39,ref b);
}
if a.len()>=256&&b.len()>=256{break;}
return (array![].span(),array![].span());
}
let w15=w15&mk0;let w16=w16&mk1;let w17=w17&mk2;
let w18=w18&mk0;let w19=w19&mk1;let w20=w20&mk2;
let(x15,y15)=maa(w15,n64);let(x16,y16)=maa(w16,n64);let(x17,y17)=maa(w17,n64);
let(x18,y18)=maa(w18,n64);let(x19,y19)=maa(w19,n64);let(x20,y20)=maa(w20,n64);
let(ie,oe,ob,ag,bg,ic,cg,dg)=uaa(x15,x16,x17,n24,n8,n16);
let(eg,fg,oc,gg,hg,od,ig,jg)=uaa(x18,x19,x20,n24,n8,n16);
let(b40,b41,b42,b43,b44,b45,b46,b47)=uaa(y15,y16,y17,n24,n8,n16);
let(b48,b49,b50,b51,b52,b53,b54,b55)=uaa(y18,y19,y20,n24,n8,n16);
let bad=ib+wt(w15,k0,t0)+wt(w16,k1,t1)+wt(w17,k2,t2)+wt(w18,k0,t0)+wt(w19,k1,t1)+wt(w20,k2,t2);
if bad==0{
nab(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,a32,a33,a34,a35,a36,a37,a38,oa,ie,oe,ob,ag,bg,ic,cg,dg,eg,fg,oc,gg,hg,od,ig,jg);
nab(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39,b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55);
}else{
core::gas::withdraw_gas().unwrap();
let v:u256=bad.into();
let(_,la)=zq::div_rem(v.low,Ut);
let ca=match constrain::<_,0x800000,Qn>(la){Ok(l)=>zu::<_,ZF>(l)==0||pt5(a2,a10,a18,a26,a34,T5)+pt5(ob,oc,a5,a13,a21,T5)+pt4(a29,a37,ic,od,T5)==0,Err(_)=>false};
if ca{
nab(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,a32,a33,a34,a35,a36,a37,a38,oa,ie,oe,ob,ag,bg,ic,cg,dg,eg,fg,oc,gg,hg,od,ig,jg);
}else{
let lq=af(bq);let l0=af(ia);let l1=af(ib);let la:ZF=zu(la);
if lq==0{vaa(ref a,a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15);}else{cab(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,ref a);}
if l0==lq{vaa(ref a,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31);}else{cab(a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31,ref a);}
if l1==l0{oac(ref a,a32,a33,a34,a35,a36,a37,a38,oa);}else{rad(a32,a33,a34,a35,a36,a37,a38,oa,ref a);}
if la==l1{vaa(ref a,ie,oe,ob,ag,bg,ic,cg,dg,eg,fg,oc,gg,hg,od,ig,jg);}else{cab(ie,oe,ob,ag,bg,ic,cg,dg,eg,fg,oc,gg,hg,od,ig,jg,ref a);}
}
let cb=v.high==0&&match constrain::<_,0x8000000000000000000000,TC>(v.low){Ok(l)=>match constrain::<_,0x800000000000000000,UC>(l){Ok(_)=>true,Err(_)=>pt5(b2,b10,b18,b26,b34,T5)+pt5(b42,b50,b5,b13,b21,T5)+pt4(b29,b37,b45,b53,T5)==0},Err(_)=>false};
if cb{
nab(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39,b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55);
}else{
if bcl(bq){vaa(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15);}else{cab(b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,ref b);}
if bcl(ia-bq){vaa(ref b,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31);}else{cab(b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,ref b);}
if bcl(ib-ia){oac(ref b,b32,b33,b34,b35,b36,b37,b38,b39);}else{rad(b32,b33,b34,b35,b36,b37,b38,b39,ref b);}
if bcl(bad-ib){vaa(ref b,b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55);}else{cab(b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55,ref b);}
}
}
let rc=if a.len()>=216{
(g1,crate::k2::htbp())
}else{
(g1,crate::k2::hfull())
};
st=lab(st,rc);
}
(a.span().slice(0,256),b.span().slice(0,256))
}
#[inline(always)]
fn pkh(a:u128,b:u128,ma:u128,mb:u128)->u128{
let f:ZF=Into::<u128,ZF>::into(a&ma)*0x800000000000010f7ffffffffffffef00000000000000000000000000000001+(b&mb).into();
f.try_into().unwrap()
}
#[derive(Copy,Drop)]
struct Tn{n64:NonZero<ZU<0x10000000000000000>>,n24:NonZero<ZU<0x1000000>>,n8:NonZero<ZU<0x100>>,n16:NonZero<ZU<0x10000>>,mk0:u128,mk1:u128,mk2:u128,k0h:u128,k1h:u128,k2h:u128,t0h:u128,t1h:u128,t2h:u128,all:crate::k2::Zl}
const Ri:Tn=Tn{n64:Wg,n24:Qk,n8:N8,n16:Yf,mk0:H0,mk1:H1,mk2:H2,k0h:Pp,k1h:Qp,k2h:Rp,t0h:Sp,t1h:Tp,t2h:Up,all:crate::k2::Rk};
#[inline(never)]
fn xaa(st:@[u128;25],ref b:Array<Za>,c:Box<Tn>){
core::gas::withdraw_gas().unwrap();
let Tn{n64,n24,n8,n16,mk0,mk1,mk2,k0h,k1h,k2h,t0h,t1h,t2h,all}=c.unbox();
fad(st,ref b,n64,n24,n8,n16,mk0,mk1,mk2,k0h,k1h,k2h,t0h,t1h,t2h,all);
}
#[inline(always)]
fn fad(st:@[u128;25],ref b:Array<Za>,n64:NonZero<ZU<0x10000000000000000>>,n24:NonZero<ZU<0x1000000>>,n8:NonZero<ZU<0x100>>,n16:NonZero<ZU<0x10000>>,mk0:u128,mk1:u128,mk2:u128,k0h:u128,k1h:u128,k2h:u128,t0h:u128,t1h:u128,t2h:u128,all:crate::k2::Zl){
let[w0,w1,w2,w3,w4,w5,w6,w7,w8,w9,w10,w11,w12,w13,w14,w15,w16,w17,w18,w19,w20,_,_,_,_]=crate::k2::rda(*st,all);
let h0=mk0;let h1=mk1;let h2=mk2;let pk0:u128=0x1fff001fff001fff001fff001fff;let ia:u128=0x1fff001fff001fff001fff0020;let oa:u128=0x1fff001fff001fff001fff001fff01;let ib:u128=0x800000800000800000800000800000;let ob:u128=0x8000008000008000008000008000;let ic:u128=0x80000080000080000080000080000080;
let p0=pkh(w0,w1,h0,h1);
let p1=pkh(w2,w3,h2,h0);
let p2=pkh(w4,w5,h1,h2);
let r0=wt(p0,pk0,ib)+wt(p1,ia,ob)+wt(p2,oa,ic);
let(q,b0)=aaa::<_,_,0xffffffffffffffffffffffffff,16777215>(p0,n24);
let(q,b1)=aaa::<_,_,0xffffffffffffffffffff,16777215>(q,n24);
let(q,b2)=aaa::<_,_,0xffffffffffffff,16777215>(q,n24);
let(q,b3)=aaa::<_,_,4294967295,16777215>(q,n24);
let(q,b4)=aaa::<_,_,255,16777215>(q,n24);
let s5=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(p1,n16);
let b5:Za=gaa::<_,_,0,16777215>(s5,kaa::<_,_,0,16776960>(r,U8));
let(q,b6)=aaa::<_,_,0xffffffffffffffffffffff,16777215>(q,n24);
let(q,b7)=aaa::<_,_,0xffffffffffffffff,16777215>(q,n24);
let(q,b8)=aaa::<_,_,0xffffffffff,16777215>(q,n24);
let(q,b9)=aaa::<_,_,65535,16777215>(q,n24);
let s10=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(p2,n8);
let b10:Za=gaa::<_,_,0,16777215>(s10,kaa::<_,_,0,16711680>(r,U16));
let(q,b11)=aaa::<_,_,0xffffffffffffffffffffffff,16777215>(q,n24);
let(q,b12)=aaa::<_,_,0xffffffffffffffffff,16777215>(q,n24);
let(q,b13)=aaa::<_,_,0xffffffffffff,16777215>(q,n24);
let(q,b14)=aaa::<_,_,16777215,16777215>(q,n24);
let b15=q;
let p0=pkh(w6,w7,h0,h1);
let p1=pkh(w8,w9,h2,h0);
let p2=pkh(w10,w11,h1,h2);
let r1=r0+wt(p0,pk0,ib)+wt(p1,ia,ob)+wt(p2,oa,ic);
let(q,b16)=aaa::<_,_,0xffffffffffffffffffffffffff,16777215>(p0,n24);
let(q,b17)=aaa::<_,_,0xffffffffffffffffffff,16777215>(q,n24);
let(q,b18)=aaa::<_,_,0xffffffffffffff,16777215>(q,n24);
let(q,b19)=aaa::<_,_,4294967295,16777215>(q,n24);
let(q,b20)=aaa::<_,_,255,16777215>(q,n24);
let s5=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(p1,n16);
let b21:Za=gaa::<_,_,0,16777215>(s5,kaa::<_,_,0,16776960>(r,U8));
let(q,b22)=aaa::<_,_,0xffffffffffffffffffffff,16777215>(q,n24);
let(q,b23)=aaa::<_,_,0xffffffffffffffff,16777215>(q,n24);
let(q,b24)=aaa::<_,_,0xffffffffff,16777215>(q,n24);
let(q,b25)=aaa::<_,_,65535,16777215>(q,n24);
let s10=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(p2,n8);
let b26:Za=gaa::<_,_,0,16777215>(s10,kaa::<_,_,0,16711680>(r,U16));
let(q,b27)=aaa::<_,_,0xffffffffffffffffffffffff,16777215>(q,n24);
let(q,b28)=aaa::<_,_,0xffffffffffffffffff,16777215>(q,n24);
let(q,b29)=aaa::<_,_,0xffffffffffff,16777215>(q,n24);
let(q,b30)=aaa::<_,_,16777215,16777215>(q,n24);
let b31=q;
if b.len()>=224&&r1==0{fac(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31);return;}
let w12=w12&mk0;let w13=w13&mk1;let w14=w14&mk2;
let(_,y12)=maa(w12,n64);let(_,y13)=maa(w13,n64);let(_,y14)=maa(w14,n64);
let(b32,b33,b34,b35,b36,b37,b38,b39)=uaa(y12,y13,y14,n24,n8,n16);
let r2=r1+wt(w12,k0h,t0h)+wt(w13,k1h,t1h)+wt(w14,k2h,t2h);
if b.len()>=216&&r2==0{gac(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39);return;}
let p0=pkh(w15,w16,h0,h1);
let p1=pkh(w17,w18,h2,h0);
let p2=pkh(w19,w20,h1,h2);
let bad=r2+wt(p0,pk0,ib)+wt(p1,ia,ob)+wt(p2,oa,ic);
let(q,b40)=aaa::<_,_,0xffffffffffffffffffffffffff,16777215>(p0,n24);
let(q,b41)=aaa::<_,_,0xffffffffffffffffffff,16777215>(q,n24);
let(q,b42)=aaa::<_,_,0xffffffffffffff,16777215>(q,n24);
let(q,b43)=aaa::<_,_,4294967295,16777215>(q,n24);
let(q,b44)=aaa::<_,_,255,16777215>(q,n24);
let s5=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(p1,n16);
let b45:Za=gaa::<_,_,0,16777215>(s5,kaa::<_,_,0,16776960>(r,U8));
let(q,b46)=aaa::<_,_,0xffffffffffffffffffffff,16777215>(q,n24);
let(q,b47)=aaa::<_,_,0xffffffffffffffff,16777215>(q,n24);
let(q,b48)=aaa::<_,_,0xffffffffff,16777215>(q,n24);
let(q,b49)=aaa::<_,_,65535,16777215>(q,n24);
let s10=q;
let(q,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(p2,n8);
let b50:Za=gaa::<_,_,0,16777215>(s10,kaa::<_,_,0,16711680>(r,U16));
let(q,b51)=aaa::<_,_,0xffffffffffffffffffffffff,16777215>(q,n24);
let(q,b52)=aaa::<_,_,0xffffffffffffffffff,16777215>(q,n24);
let(q,b53)=aaa::<_,_,0xffffffffffff,16777215>(q,n24);
let(q,b54)=aaa::<_,_,16777215,16777215>(q,n24);
let b55=q;
if bad==0{nab(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,b32,b33,b34,b35,b36,b37,b38,b39,b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55);}else{if r0==0{vaa(ref b,b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15);}else{cab(b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,ref b);}if r1==r0{vaa(ref b,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31);}else{cab(b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31,ref b);}if r2==r1{oac(ref b,b32,b33,b34,b35,b36,b37,b38,b39);}else{rad(b32,b33,b34,b35,b36,b37,b38,b39,ref b);}if bad==r2{vaa(ref b,b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55);}else{cab(b40,b41,b42,b43,b44,b45,b46,b47,b48,b49,b50,b51,b52,b53,b54,b55,ref b);}}
}


#[inline(never)]
pub fn sad(r0:U64,r1:U64,r2:U64,r3:U64,l4:L4)->Span<Za>{
let mut b:Array<Za>=array![];
let g=crate::k2::KG;
yac([hx(r0),hx(r1),hx(r2),hx(r3),zu(kaa::<_,_,0x1f00000000000000000000,0x1f03040000000000000000>(l4,Vp)),0,0,0,g,0,0,0,0,0,g,0,g,0,0,0,0x80000000000000000000000000000000,0,g,0,0],ref b);
b.span().slice(0,256)
}
#[inline(never)]
pub fn pairx(r0:U64,r1:U64,r2:U64,r3:U64,i:ZB<0,14>)->(Span<Za>,Span<Za>){
let(r,s)=aaa::<_,_,3,3>(i,N4);
let l:ZB<0x1f0000,0x1f0303>=gaa(gaa::<_,_,0,0x303>(s,kaa::<_,_,0,0x300>(r,U8)),ZC);
(sad(r0,r1,r2,r3,zu(l)),sad(r0,r1,r2,r3,zu(gaa::<_,_,0x1f0001,0x1f0304>(l,U1))))
}
type L4=ZB<0x1f0000,0x1f0304>;
const N4:NonZero<ZU<4>>=4;
const ZC:ZU<0x1f0000>=0x1f0000;
const U1:ZU<1>=1;
#[inline(always)]
fn hx(r:U64)->u128{
zu(kaa::<_,_,0,0xffffffffffffffff0000000000000000>(r,Vp))
}
fn yac(st:[u128;25],ref b:Array<Za>){
let mut st=st;
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let n24:NonZero<ZU<0x1000000>>=Qk;
let n8:NonZero<ZU<0x100>>=N8;
let n16:NonZero<ZU<0x10000>>=Yf;
while b.len()<256{
st=naa(st);
xaa(@st,ref b,BoxTrait::new(Ri));
}
}
impl VN of ZD<u128,ZU<2>>{type DivT=ZB<0,0x7fffffffffffffffffffffffffffffff>;type RemT=ZB<0,1>;}
const N2:NonZero<ZU<2>>=2;
#[inline(always)]
fn oab(r:U64)->u128{
zu(kaa::<_,_,0,0xffffffffffffffffffffffffffffffff>(r,PD))
}
const PD:ZU<0x10000000000000001>=0x10000000000000001;
const QD:ZU<0x1f00000000000000000000>=0x1f00000000000000000000;
#[inline(always)]
pub(crate)fn uab(r0:U64,r1:U64,r2:U64,r3:U64,first:u128,ref out:Array<Span<Za>>){
let q0=oab(r0);let q1=oab(r1);let q2=oab(r2);let q3=oab(r3);
let h=crate::k2::lad(q0,q1,q2,q3);
let all=crate::k2::Rk;
let kx=crate::k2::aaj(h,all);
let g1=crate::k2::g1z();
let g1y=crate::k2::g1y();
if first==0{
let(a,b)=aac(h,kx,(0x1f000100000000001f0000,0x100000000001f000000000000001f00),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,0);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
}
let(a,b)=aac(h,kx,(0x1f000300000000001f0002,0x300000000001f000200000000001f00),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,2);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f010100000000001f0100,0x100000000001f010000000000001f01),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,4);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f010300000000001f0102,0x300000000001f010200000000001f01),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,6);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f020100000000001f0200,0x100000000001f020000000000001f02),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,8);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f020300000000001f0202,0x300000000001f020200000000001f02),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,10);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f030100000000001f0300,0x100000000001f030000000000001f03),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,12);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
let(a,b)=aac(h,kx,(0x1f030300000000001f0302,0x300000000001f030200000000001f03),all,g1,g1y);
if a.len()==0{let(x,y)=pairx(r0,r1,r2,r3,14);out.p(x);out.p(y);}else{out.p(a);out.p(b);}
}
#[inline(always)]
fn wap(mut st:[u128;25],ref b:Array<Za>,ref src:Span<U64>,g1:Box<[u128;13]>)->[u128;25]{
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let n24:NonZero<ZU<0x1000000>>=Qk;
let n8:NonZero<ZU<0x100>>=N8;
let n16:NonZero<ZU<0x10000>>=Yf;
let mk0:u128=H0;let mk1:u128=H1;let mk2:u128=H2;let k0h:u128=Pp;let k1h:u128=Qp;let k2h:u128=Rp;let t0h:u128=Sp;let t1h:u128=Tp;let t2h:u128=Up;let all=crate::k2::Rk;
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st
}
#[inline(always)]
fn xap(mut st:[u128;25],ref b:Array<Za>,ref src:Span<U64>,g1:Box<[u128;13]>)->[u128;25]{
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let n24:NonZero<ZU<0x1000000>>=Qk;
let n8:NonZero<ZU<0x100>>=N8;
let n16:NonZero<ZU<0x10000>>=Yf;
let mk0:u128=H0;let mk1:u128=H1;let mk2:u128=H2;let k0h:u128=Pp;let k1h:u128=Qp;let k2h:u128=Rp;let t0h:u128=Sp;let t1h:u128=Tp;let t2h:u128=Up;let all=crate::k2::Rk;
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=yaa(st,ref src);
st
}
#[inline(always)]
fn lpk(x:u128,y:u128)->u128{
let v:ZF=x.into()+y.into()*0x10000000000000000;
v.try_into().unwrap()
}
pub(crate)fn xai(lanes:Span<U64>)->(Array<u128>,Span<Za>,Span<Za>){
let mut src=lanes;
let[k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10,k11,k12,k13,k14,k15,k16]=(*src.multi_pop_front::<17>().unwrap()).unbox();
let(u0,u1,u2,u3,u4)=(k0,k1,k2,k3,k4);
let(k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10,k11,k12,k13,k14,k15,k16):(u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128,u128)=(zu(k0),zu(k1),zu(k2),zu(k3),zu(k4),zu(k5),zu(k6),zu(k7),zu(k8),zu(k9),zu(k10),zu(k11),zu(k12),zu(k13),zu(k14),zu(k15),zu(k16));
let mut st=[oab(u0),oab(u1),oab(u2),oab(u3),zu(gaa::<_,_,0x1f00000000000000000000,0x1f0000ffffffffffffffff>(u4,QD)),k5,k6,k7,nt(k8),k9,k10,k11,k12,k13,nt(k14),k15,nt(k16),0,0,0,0x80000000000000000000000000000000,0,0xffffffffffffffffffffffffffffffff,0,0];
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let n24:NonZero<ZU<0x1000000>>=Qk;
let n8:NonZero<ZU<0x100>>=N8;
let n16:NonZero<ZU<0x10000>>=Yf;
let mut b:Array<Za>=array![];
let g1=crate::k2::g1z();
st=wap(st,ref b,ref src,g1);
if b.len()<256{
yac(st,ref b);
}
let a0=b.span().slice(0,256);
st=wah(st,k0,k1,k2,k3);
let mut b:Array<Za>=array![];
st=xap(st,ref b,ref src,g1);
st=lab(st,(g1,crate::k2::hfull()));
xaa(@st,ref b,BoxTrait::new(Ri));
st=lab(gad(st,ref src),(g1,crate::k2::htbp()));
xaa(@st,ref b,BoxTrait::new(Ri));
if b.len()<256{
let mut l=lanes;
let[r0,r1,r2,r3]=(*l.multi_pop_front::<4>().unwrap()).unbox();
b=array![];
b.append_span(sad(r0,r1,r2,r3,0x1f0001));
}
let[q0,q1,q2,q3,q4,q5,q6,q7,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_]=st;
let mut tr:Array<u128>=array![];
let l0=q0&LO;tr.p(l0);
let l1=q1&LO;tr.p(l1);
let l2=q2&LO;tr.p(l2);
let l3=q3&LO;tr.p(l3);
let l4=q4&LO;tr.p(l4);
let l5=q5&LO;tr.p(l5);
let l6=q6&LO;tr.p(l6);
let l7=q7&LO;tr.p(l7);
(tr,a0,b.span().slice(0,256))
}
#[inline(always)]
fn wah(st:[u128;25],r0:u128,r1:u128,r2:u128,r3:u128)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=st;
let x0=a0&LO;let x1=a1&LO;let x2=a2&LO;let x3=a3&LO;let x4=a4&LO;let x5=a5&LO;let x6=a6&LO;let x7=a7&LO;let x8=a8|0xffffffffffffffff0000000000000000;let x9=a9&LO;let x10=a10&LO;let x11=a11&LO;let x12=a12&LO;let x13=a13&LO;let x14=a14|0xffffffffffffffff0000000000000000;let x15=a15&LO;let x16=a16|0xffffffffffffffff0000000000000000;let x17=a17&LO;let x18=a18&LO;let x19=a19&LO;let x20=a20&LO;let x21=a21&LO;let x22=a22|0xffffffffffffffff0000000000000000;let x23=a23&LO;let x24=a24&LO;
[lpk(x0,r0),lpk(x1,r1),lpk(x2,r2),lpk(x3,r3),x4+0x1f00010000000000000000,x5,x6,x7,x8,x9,x10,x11,x12,x13,x14,x15,x16,x17,x18,x19,x20+0x80000000000000000000000000000000,x21,x22,x23,x24]
}
#[inline(always)]
fn yaa(st:[u128;25],ref src:Span<U64>)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=st;
let[k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10,k11,k12,k13,k14,k15,k16]=(*src.multi_pop_front::<17>().unwrap()).unbox();
[a0^zu(k0),a1^zu(k1),a2^zu(k2),a3^zu(k3),a4^zu(k4),a5^zu(k5),a6^zu(k6),a7^zu(k7),a8^zu(k8),a9^zu(k9),a10^zu(k10),a11^zu(k11),a12^zu(k12),a13^zu(k13),a14^zu(k14),a15^zu(k15),a16^zu(k16),a17,a18,a19,a20,a21,a22,a23,a24]
}
#[inline(always)]
fn gad(st:[u128;25],ref src:Span<U64>)->[u128;25]{
let[a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24]=st;
let[k0,k1,k2,k3,k4,k5,k6,k7,k8,k9,k10]=(*src.multi_pop_front::<11>().unwrap()).unbox();
[a0^zu(k0),a1^zu(k1),a2^zu(k2),a3^zu(k3),a4^zu(k4),a5^zu(k5),a6^zu(k6),a7^zu(k7),a8^zu(k8),a9^zu(k9),a10^zu(k10),a11^0x1f,a12,a13,a14,a15,a16^0x8000000000000000,a17,a18,a19,a20,a21,a22,a23,a24]
}
pub(crate)fn cai(tr:Span<u128>,m:[u128;5],c:[U64;4])->(Array<u64>,Array<u32>){
let mut tr=tr;
let[t0,t1,t2,t3,t4,t5,t6,t7]=(*tr.multi_pop_front::<8>().unwrap()).unbox();
let[m8,m9,m10,m11,m12]=m;
let[c0,c1,c2,c3]=c;
let st=hab(
[
lpk(t0,zu(c0)),lpk(t1,zu(c1)),lpk(t2,zu(c2)),lpk(t3,zu(c3)),t4+0x1f0000000000000000,t5,t6,t7,m8,
m9,m10,m11,m12,0,0,0,0x80000000000000008000000000000000,0,0,0,0,0,0,0,0,
],
);
let[q0,q1,q2,q3,q4,q5,q6,q7,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_,_]=st;
let mut mu:Array<u64>=array![];
let(h0,l0)=zq::div_rem(q0,Wg);
mu.p(zu(l0));
let(h1,l1)=zq::div_rem(q1,Wg);
mu.p(zu(l1));
let(h2,l2)=zq::div_rem(q2,Wg);
mu.p(zu(l2));
let(h3,l3)=zq::div_rem(q3,Wg);
mu.p(zu(l3));
let(h4,l4)=zq::div_rem(q4,Wg);
mu.p(zu(l4));
let(h5,l5)=zq::div_rem(q5,Wg);
mu.p(zu(l5));
let(h6,l6)=zq::div_rem(q6,Wg);
mu.p(zu(l6));
let(h7,l7)=zq::div_rem(q7,Wg);
mu.p(zu(l7));
let pab=crate::sa0::uah(h0,[h1,h2,h3,h4,h5,h6,h7].span());
if pab.len()==0{
return (mu,cold_ball(c0,c1,c2,c3));
}
(mu,pab)
}
type ZF=felt252;

/// SampleInBall continuation when the first SHAKE256 block of c~ does not yield tau positions (never on
/// valid inputs in practice): out of line with its own gas withdrawal so the common path is not charged for it.
#[inline(never)]
fn cold_ball(c0:U64,c1:U64,c2:U64,c3:U64)->Array<u32>{
core::gas::withdraw_gas().unwrap();
cbr([hx(c0),hx(c1),hx(c2),hx(c3),0x1f0000000000000000,0,0,0,0,0,0,0,0,0,0,0,0x80000000000000000000000000000000,0,0,0,0,0,0,0,0],0,array![],true)
}
/// One squeeze step of the cold SampleInBall fallback: permute, append this block's words, retry the sampler.
#[inline(never)]
fn cbr(st:[u128;25],signs:U64,words:Array<U64>,first:bool)->Array<u32>{
core::gas::withdraw_gas().unwrap();
let st=keccak_f1600_x2(st);
let n64:NonZero<ZU<0x10000000000000000>>=Wg;
let mut signs=signs;let mut words=words;let mut first=first;
for x in st.span().slice(0,17){let(_,h)=maa(*x,n64);if first{signs=h;first=false;}else{words.p(h);}}
let r=crate::sa0::uah(signs,words.span());
if r.len()!=0{return r;}
cbr(st,signs,words,false)
}
