use crate::k2::Ap;
use crate::kc0::{SHAKE256_RATE,absorb};
const TAU:u32=39;
use corelib_imports::bounded_int::{BoundedInt as ZB,DivRemHelper as ZD,UnitInt as ZU,bounded_int as zq,upcast as zu};
use core::internal::bounded_int::{ConstrainHelper,constrain};
const Th:NonZero<ZU<0x1000000>>=0x1000000;
const Rm:NonZero<ZU<0x100>>=0x100;
const Vo:NonZero<ZU<0x10000>>=0x10000;
type U64=ZB<0,0xffffffffffffffff>;
pub(crate)type Za=ZB<0,0xffffff>;
type Qn=ZB<0,0x7fffff>;
type B1=ZB<0,1>;
type Rn=ZB<0,0xffffffffff>;
type Pk=ZB<0,0xffff>;
type R8=ZB<0,0xff>;
type Wo=ZB<0,0xffffffffffffff>;
type Sn=ZB<0,0xffffffffffff>;
impl XM of ZD<U64,ZU<0x1000000>>{type DivT=Rn;type RemT=Za;}
impl QI of ZD<Rn,ZU<0x1000000>>{type DivT=Pk;type RemT=Za;}
impl D8 of ZD<U64,ZU<0x100>>{type DivT=Wo;type RemT=R8;}
impl RI of ZD<Wo,ZU<0x1000000>>{type DivT=ZB<0,0xffffffff>;type RemT=Za;}
impl SI of ZD<ZB<0,0xffffffff>,ZU<0x1000000>>{type DivT=R8;type RemT=Za;}
impl YM of ZD<U64,ZU<0x10000>>{type DivT=Sn;type RemT=Pk;}
impl TI of ZD<Sn,ZU<0x1000000>>{type DivT=Za;type RemT=Za;}
impl ZM of ZD<Za,ZU<0x800000>>{type DivT=B1;type RemT=Qn;}
impl KQ of ConstrainHelper<Qn,8380417>{
type LowT=ZB<0,8380416>;
type HighT=ZB<8380417,0x7fffff>;
}
type Xo=ZB<0,0xffffffffffffffffffffffffff>;
type Pt=ZB<0,0xffffffffffffffffffff>;
type Yo=ZB<0,0xffffffffffffffffffffffffffffff>;
type Qt=ZB<0,0xffffffffffffffffffffffff>;
type Rt=ZB<0,0xffffffffffffffffff>;
type Zo=ZB<0,0xffffffffffffffffffffffffffff>;
type St=ZB<0,0xffffffffffffffffffffff>;
impl UI of ZD<u128,ZU<0x1000000>>{type DivT=Xo;type RemT=Za;}
impl VI of ZD<Xo,ZU<0x1000000>>{type DivT=Pt;type RemT=Za;}
impl PN of ZD<u128,ZU<0x100>>{type DivT=Yo;type RemT=R8;}
impl WI of ZD<Yo,ZU<0x1000000>>{type DivT=Qt;type RemT=Za;}
impl XI of ZD<Qt,ZU<0x1000000>>{type DivT=Rt;type RemT=Za;}
impl YI of ZD<u128,ZU<0x10000>>{type DivT=Zo;type RemT=Pk;}
impl ZI of ZD<Zo,ZU<0x1000000>>{type DivT=St;type RemT=Za;}
#[inline(always)]
pub(crate)fn candidates(l0:u128,l1:u128,l2:u128,ref a:Array<Za>){
let(x,c0)=zq::div_rem(l0,Th);
let(c2_low,c1)=zq::div_rem(x,Th);
let(x,c2_high)=zq::div_rem(l1,Rm);
let(x,c3)=zq::div_rem(x,Th);
let(c5_low,c4)=zq::div_rem(x,Th);
let(x,c5_high)=zq::div_rem(l2,Vo);
let(c7,c6)=zq::div_rem(x,Th);
keep(c0,ref a);
keep(c1,ref a);
let c2:ZF=zu::<Pt,ZF>(c2_low)+zu::<R8,ZF>(c2_high)*0x10000;
keep(c2.try_into().unwrap(),ref a);
keep(c3,ref a);
keep(c4,ref a);
let c5:ZF=zu::<Rt,ZF>(c5_low)+zu::<Pk,ZF>(c5_high)*0x100;
keep(c5.try_into().unwrap(),ref a);
keep(c6,ref a);
let c7:ZF=zu::<St,ZF>(c7);
keep(c7.try_into().unwrap(),ref a);
}
impl K1 of ConstrainHelper<Za,8380417>{
type LowT=ZB<0,8380416>;
type HighT=ZB<8380417,0xffffff>;
}
impl K2 of ConstrainHelper<ZB<8380417,0xffffff>,0x800000>{
type LowT=ZB<8380417,0x7fffff>;
type HighT=ZB<0x800000,0xffffff>;
}
impl K3 of ConstrainHelper<ZB<0x800000,0xffffff>,16769025>{
type LowT=ZB<0x800000,16769024>;
type HighT=ZB<16769025,0xffffff>;
}
#[inline(always)]
pub(crate)fn keep(candidate:Za,ref a:Array<Za>){
if let Ok(c)=constrain::<Za,8380417>(candidate){
a.p(zu(c));
}
}
pub fn expand_a(rho:Span<u8>)->Array<Span<Za>>{
let mut b=rho;
let mut lanes:Array<u128>=array![];
let mut l=0;
while l !=4{
let mut v:u128=0;
let mut scale:u128=1;
let mut k=0;
while k !=8{
v+=(*b.pop_front().unwrap()).into()*scale;
if k !=7{
scale*=256;
}
k+=1;
}
lanes.p(v);
l+=1;
}
nac(*lanes.at(0),*lanes.at(1),*lanes.at(2),*lanes.at(3))
}
pub fn nac(r0:u128,r1:u128,r2:u128,r3:u128)->Array<Span<Za>>{
let mut out:Array<Span<Za>>=array![];
crate::x2::uab(corelib_imports::bounded_int::downcast(r0).unwrap(),corelib_imports::bounded_int::downcast(r1).unwrap(),corelib_imports::bounded_int::downcast(r2).unwrap(),corelib_imports::bounded_int::downcast(r3).unwrap(),0,ref out);
out
}
pub(crate)const Tt:[u128;128]=[
0x1,0x2,0x4,0x8,0x10,0x20,0x40,0x80,0x100,0x200,0x400,0x800,0x1000,0x2000,0x4000,
0x8000,0x10000,0x20000,0x40000,0x80000,0x100000,0x200000,0x400000,0x800000,0x1000000,
0x2000000,0x4000000,0x8000000,0x10000000,0x20000000,0x40000000,0x80000000,0x100000000,
0x200000000,0x400000000,0x800000000,0x1000000000,0x2000000000,0x4000000000,0x8000000000,
0x10000000000,0x20000000000,0x40000000000,0x80000000000,0x100000000000,0x200000000000,
0x400000000000,0x800000000000,0x1000000000000,0x2000000000000,0x4000000000000,
0x8000000000000,0x10000000000000,0x20000000000000,0x40000000000000,0x80000000000000,
0x100000000000000,0x200000000000000,0x400000000000000,0x800000000000000,
0x1000000000000000,0x2000000000000000,0x4000000000000000,0x8000000000000000,
0x10000000000000000,0x20000000000000000,0x40000000000000000,0x80000000000000000,
0x100000000000000000,0x200000000000000000,0x400000000000000000,0x800000000000000000,
0x1000000000000000000,0x2000000000000000000,0x4000000000000000000,0x8000000000000000000,
0x10000000000000000000,0x20000000000000000000,0x40000000000000000000,0x80000000000000000000,
0x100000000000000000000,0x200000000000000000000,0x400000000000000000000,0x800000000000000000000,
0x1000000000000000000000,0x2000000000000000000000,0x4000000000000000000000,0x8000000000000000000000,
0x10000000000000000000000,0x20000000000000000000000,0x40000000000000000000000,0x80000000000000000000000,
0x100000000000000000000000,0x200000000000000000000000,0x400000000000000000000000,0x800000000000000000000000,
0x1000000000000000000000000,0x2000000000000000000000000,0x4000000000000000000000000,0x8000000000000000000000000,
0x10000000000000000000000000,0x20000000000000000000000000,0x40000000000000000000000000,0x80000000000000000000000000,
0x100000000000000000000000000,0x200000000000000000000000000,0x400000000000000000000000000,0x800000000000000000000000000,
0x1000000000000000000000000000,0x2000000000000000000000000000,0x4000000000000000000000000000,0x8000000000000000000000000000,
0x10000000000000000000000000000,0x20000000000000000000000000000,0x40000000000000000000000000000,0x80000000000000000000000000000,
0x100000000000000000000000000000,0x200000000000000000000000000000,0x400000000000000000000000000000,0x800000000000000000000000000000,
0x1000000000000000000000000000000,0x2000000000000000000000000000000,0x4000000000000000000000000000000,0x8000000000000000000000000000000,
0x10000000000000000000000000000000,0x20000000000000000000000000000000,0x40000000000000000000000000000000,0x80000000000000000000000000000000,
];
pub fn xab(l0:u128,l1:u128,l2:u128,l3:u128)->Array<u32>{
let h:u128=0x10000000000000000;
ball_offsets(
crate::k2::keccak_f1600_x2(
[l0*h,l1*h,l2*h,l3*h,0x1f*h,0,0,0,0,0,0,0,0,0,0,0,0x8000000000000000*h,0,0,0,0,0,0,0,0],
),
)
}
pub fn fab(c_tilde:Span<u8>)->Array<u32>{
let[s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15,s16,s17,s18,s19,s20,s21,s22,s23,s24]=absorb(c_tilde,SHAKE256_RATE);
let h:u128=0x10000000000000000;
ball_offsets([s0*h,s1*h,s2*h,s3*h,s4*h,s5*h,s6*h,s7*h,s8*h,s9*h,s10*h,s11*h,s12*h,s13*h,s14*h,s15*h,s16*h,s17*h,s18*h,s19*h,s20*h,s21*h,s22*h,s23*h,s24*h])
}
impl PJ of ZD<u128,ZU<0x10000000000000000>>{type DivT=U64;type RemT=U64;}
impl QJ of ZD<Wo,ZU<0x100>>{type DivT=Sn;type RemT=R8;}
impl RJ of ZD<Sn,ZU<0x100>>{type DivT=Rn;type RemT=R8;}
impl SJ of ZD<Rn,ZU<0x100>>{type DivT=ZB<0,0xffffffff>;type RemT=R8;}
impl TJ of ZD<ZB<0,0xffffffff>,ZU<0x100>>{type DivT=Za;type RemT=R8;}
impl UJ of ZD<Za,ZU<0x100>>{type DivT=Pk;type RemT=R8;}
impl VJ of ZD<Pk,ZU<0x100>>{type DivT=R8;type RemT=R8;}
impl WJ of ZD<U64,ZU<0x100000000>>{type DivT=ZB<0,0xffffffff>;type RemT=ZB<0,0xffffffff>;}
const Ty:NonZero<ZU<0x100000000>>=0x100000000;
impl Zy of ZD<U64,ZU<2>>{type DivT=ZB<0,0x7fffffffffffffff>;type RemT=B1;}
impl XJ of ConstrainHelper<R8,128>{type LowT=ZB<0,127>;type HighT=ZB<128,255>;}
impl RN of corelib_imports::bounded_int::bounded_int::SubHelper<ZB<128,255>,ZU<128>>{type Result=ZB<0,127>;}
impl YJ of corelib_imports::bounded_int::MulHelper<B1,ZU<256>>{type Result=ZB<0,256>;}
impl ZJ of corelib_imports::bounded_int::AddHelper<ZB<0,256>,ZU<256>>{type Result=ZB<256,512>;}
impl PK of corelib_imports::bounded_int::bounded_int::SubHelper<ZB<256,512>,R8>{type Result=ZB<1,512>;}
/// A hit on position `j` (bit `b` of the half whose sign bits are `sj`): position `i` takes the
/// sign `j` held and `j` takes the new sign `sb`. When the two signs agree the entry for `j` is
/// already right and only `i` is appended; otherwise the one stale entry for `j` is dropped by
/// `ball_flip`. Returns the updated `sj` and the sign bit to add for `i` in the upper half.
#[inline(never)]
fn uac(ref taa:Array<u32>,ref hi:u128,sj:ZF,i:u32,j:u32,off:u32,sb:B1,b:u128)->(ZF,ZF){
let oa:u128=sj.try_into().unwrap();
let ia=oa&b!=0;
let new=zu::<_,ZF>(sb)==1;
let bi=*Tt.span().at(i-128);
let add=if ia{bi.into()}else{0};
hi=hi+bi;
if ia==new{
taa.p(off+j-i);
return (sj,add);
}
let(bab,moved)=if ia{(512-j,512-i)}else{(256-j,256-i)};
vad(ref taa,bab,off,moved);
if new{(sj+b.into(),add)}else{(sj-b.into(),add)}
}
/// Rebuilds `list` without the entry `stale`, then appends `off` and `moved`.
#[inline(always)]fn vad(ref taa:Array<u32>,bab:u32,off:u32,moved:u32){
taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);taa.p(bab);
let mut sp=taa.span();
let mut new:Array<u32>=array![];
while let Some(c)=sp.multi_pop_front::<12>(){
let[e0,e1,e2,e3,e4,e5,e6,e7,e8,e9,e10,e11]=(*c).unbox();
if e0!=bab{new.p(e0);}
if e1!=bab{new.p(e1);}
if e2!=bab{new.p(e2);}
if e3!=bab{new.p(e3);}
if e4!=bab{new.p(e4);}
if e5!=bab{new.p(e5);}
if e6!=bab{new.p(e6);}
if e7!=bab{new.p(e7);}
if e8!=bab{new.p(e8);}
if e9!=bab{new.p(e9);}
if e10!=bab{new.p(e10);}
if e11!=bab{new.p(e11);}
}
new.p(off);
new.p(moved);
taa=new;
}
/// One SampleInBall draw: byte `j` against the current index `i` (skipped when j > i).
#[inline(always)]
fn sac(j:R8,ref signs:U64,ref lo:u128,ref hi:u128,ref slo:ZF,ref shi:ZF,ref taa:Array<u32>,ref i:u32,two:NonZero<ZU<2>>,tab:ZU<256>,yab:ZU<128>,bit:Span<u128>){
let ju:u32=zu(j);
if ju>i{
return;
}
let(rest,sb)=zq::div_rem(signs,two);
signs=zu(rest);
let off:u32=zu(zq::sub(zq::add(zq::mul(sb,tab),tab),j));
match constrain::<R8,128>(j){
Ok(jl)=>{
let b=*bit.at(zu(jl));
let(ab,_,ob)=bitwise(lo,b);
if ab==0{
lo=ob;
slo=slo+zu::<_,ZF>(sb)*b.into();
taa.p(off);
}else{
let(n,a)=uac(ref taa,ref hi,slo,i,ju,off,sb,b);
slo=n;
shi=shi+a;
}
},
Err(jh)=>{
let b=*bit.at(zu(zq::sub(jh,yab)));
let(ab,_,ob)=bitwise(hi,b);
if ab==0{
hi=ob;
shi=shi+zu::<_,ZF>(sb)*b.into();
taa.p(off);
}else{
let(n,a)=uac(ref taa,ref hi,shi,i,ju,off,sb,b);
shi=n+a;
}
},
}
i+=1;
}
pub fn ball_offsets(state:[u128;25])->Array<u32>{
let ns:NonZero<ZU<0x10000000000000000>>=0x10000000000000000;
let two:NonZero<ZU<2>>=2;
let mut ia=state.span();
let mut words=ia.slice(0,17);
let(signs,_)=zq::div_rem(*words.pop_front().unwrap(),ns);
let mut signs:U64=signs;
let mut taa:Array<u32>=array![];
let mut i:u32=256-TAU;
let mut w:U64=0;
let mut left:ZF=0;
while i!=256{
if left==0{
let x=match words.pop_front(){
Some(x)=>*x,
None=>{
ia=crate::k2::keccak_f1600_x2((*ia.multi_pop_front::<25>().unwrap()).unbox()).span();
words=ia.slice(1,16);
*ia.at(0)
},
};
let(x,_)=zq::div_rem(x,ns);
w=x;
left=8;
}
let(q,b)=zq::div_rem(w,Rm);
w=zu(q);
left-=1;
let j:u32=zu(b);
if j<=i{
let(rest,sb)=zq::div_rem(signs,two);
signs=zu(rest);
let mut new:Array<u32>=array![];
for e in taa.span(){
let o=*e;
if o==256-j{new.p(256-i);}else if o==512-j{new.p(512-i);}else{new.p(o);}
}
new.p(256+256*zu::<_,u32>(sb)-j);
taa=new;
i+=1;
}
};
taa
}
#[derive(Copy,Drop)]
struct BI{b:NonZero<ZU<2>>,c:NonZero<ZU<0x100>>,d:ZU<256>,e:ZU<128>,f:Span<u128>}
#[inline(always)]
pub(crate)fn uah(h0:U64,words:Span<U64>)->Array<u32>{
let mut signs:U64=h0;
let mut words=words;
let two:NonZero<ZU<2>>=2;
let n8:NonZero<ZU<0x100>>=Rm;
let tab:ZU<256>=256;
let yab:ZU<128>=128;
let bit=Tt.span();
let mut lo:u128=0;
let mut hi:u128=0;
let mut slo:ZF=0;
let mut shi:ZF=0;
let mut taa:Array<u32>=array![];
let mut i:u32=256-TAU;
let mut oa=false;
let mut ib:ZB<0,0xffffffff>=0;
let mut ia=false;
let bi=BI{b:two,c:n8,d:tab,e:yab,f:bit};
loop{let BI{b:two,c:n8,d:tab,e:yab,f:bit}=bi;
let w4:ZB<0,0xffffffff>=if ia{ia=false;ib}else{
let w=match words.pop_front(){Some(w)=>*w,None=>{oa=true;break;},};
let(h,l)=zq::div_rem(w,Ty);
ib=h;ia=true;l};
let(w,b0)=zq::div_rem(w4,n8);
sac(b0,ref signs,ref lo,ref hi,ref slo,ref shi,ref taa,ref i,two,tab,yab,bit);
if i==256{break;}
let(w,b1)=zq::div_rem(w,n8);
sac(b1,ref signs,ref lo,ref hi,ref slo,ref shi,ref taa,ref i,two,tab,yab,bit);
if i==256{break;}
let(b3,b2)=zq::div_rem(w,n8);
sac(b2,ref signs,ref lo,ref hi,ref slo,ref shi,ref taa,ref i,two,tab,yab,bit);
if i==256{break;}
sac(b3,ref signs,ref lo,ref hi,ref slo,ref shi,ref taa,ref i,two,tab,yab,bit);
if i==256{break;}
};
if oa{
return array![];
}
taa
}
// qalias
type ZF=felt252;

extern fn bitwise(lhs:u128,rhs:u128)->(u128,u128,u128) implicits(core::integer::Bitwise) nopanic;
