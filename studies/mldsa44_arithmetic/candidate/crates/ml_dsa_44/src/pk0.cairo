use crate::k2::Ap;
const GAMMA1:u32=131072;
const GAMMA2:u32=95232;
const W1_MOD:u32=44;
const OMEGA:u32=80;
const TWO_POW_D:u32=8192;
use corelib_imports::bounded_int::{AddHelper,BoundedInt as ZB,DivRemHelper as ZD,MulHelper,UnitInt as ZU,bounded_int as zq,upcast as zu,downcast};
use core::internal::bounded_int::{ConstrainHelper,constrain};
impl P4 of ZD<u8,ZU<4>>{type DivT=ZB<0,63>;type RemT=ZB<0,3>;}
impl Po of ZD<u8,ZU<16>>{type DivT=ZB<0,15>;type RemT=ZB<0,15>;}
impl QM of ZD<u8,ZU<64>>{type DivT=ZB<0,3>;type RemT=ZB<0,63>;}
const N4:NonZero<ZU<4>>=4;
const Yf:NonZero<ZU<16>>=16;
const Wg:NonZero<ZU<64>>=64;
type Y=ZB<0,261986>;
impl CY of ConstrainHelper<Y,130994>{type LowT=ZB<0,130993>;type HighT=ZB<130994,261986>;}
#[inline(always)]
fn f(x:u8)->ZF{
x.into()
}
pub fn wab(bytes:Span<u8>,sc:ZF,ref out:Array<ZF>){
let mut b=bytes;
while let Some(g)=b.multi_pop_front::<5>(){
let[b0,b1,b2,b3,b4]=(*g).unbox();
let(ia,oa)=zq::div_rem(b1,N4);
let(b2h,b2l)=zq::div_rem(b2,Yf);
let(ib,ob)=zq::div_rem(b3,Wg);
let b0:ZF=b0.into();
let b4:ZF=b4.into();
out.p((b0+256*zu::<_,ZF>(oa))*sc);
out.p((zu::<_,ZF>(ia)+64*zu::<_,ZF>(b2l))*sc);
out.p((zu::<_,ZF>(b2h)+16*zu::<_,ZF>(ob))*sc);
out.p((zu::<_,ZF>(ib)+4*b4)*sc);
}
}
#[inline(always)]
fn zc(x:ZF,ref out:Array<ZF>)->bool{
match downcast::<ZF,Y>(x-79){
Some(y)=>{
match constrain::<Y,130994>(y){
Ok(lo)=>out.p(130993-zu::<_,ZF>(lo)),
Err(hi)=>out.p(8380417+130993-zu::<_,ZF>(hi)),
}
true
},
None=>false,
}
}
pub fn z_unpack(bytes:Span<u8>)->Option<Array<ZF>>{
let mut out:Array<ZF>=array![];
let mut b=bytes;
while let Some(g)=b.multi_pop_front::<9>(){
let[b0,b1,b2,b3,b4,b5,b6,b7,b8]=(*g).unbox();
let(b2h,b2l)=zq::div_rem(b2,N4);
let(ia,oa)=zq::div_rem(b4,Yf);
let(ib,ob)=zq::div_rem(b6,Wg);
let x0=f(b0)+256*f(b1)+65536*zu::<_,ZF>(b2l);
let x1=zu::<_,ZF>(b2h)+64*f(b3)+16384*zu::<_,ZF>(oa);
let x2=zu::<_,ZF>(ia)+16*f(b5)+4096*zu::<_,ZF>(ob);
let x3=zu::<_,ZF>(ib)+4*f(b7)+1024*f(b8);
if !(zc(x0,ref out)&&zc(x1,ref out)&&zc(x2,ref out)&&zc(x3,ref out)){
return None;
}
}
Some(out)
}
/// HintBitUnpack validity (FIPS 204 Algorithm 21) on the 84 hint bytes: the four counts never fall and stay
/// within 80, positions strictly increase inside each polynomial, and every byte after the last count is zero.
/// FIPS 204 Alg. 21 HintBitUnpack well-formedness of the 84-byte hint field `y` (omega = 80 positions + 4 counts).
#[inline(always)]
pub fn hint_valid(y:Span<u8>)->bool{dac(y).is_some()}
/// As `hint_valid`, returning the four cumulative hint counts y[80..84] when the field is well formed.
#[inline(always)]
pub fn dac(y:Span<u8>)->Option<[u8;4]>{
if y.len()!=84{return None;}
let mut s=y;
let[e0,e1,e2,e3]=(*s.multi_pop_back::<4>().unwrap()).unbox();
if e0>e1||e1>e2||e2>e3||e3>80{return None;}
let(f0,f1,f2,f3):(ZF,ZF,ZF,ZF)=(e0.into(),e1.into(),e2.into(),e3.into());
if jac(ref s,f0)&&jac(ref s,f1-f0)&&jac(ref s,f2-f1)&&jac(ref s,f3-f2)&&aai(s){Some([e0,e1,e2,e3])}else{None}
}
/// True when the next `k` bytes of `s` strictly increase (consumes them).
fn jac(ref s:Span<u8>,k:ZF)->bool{
if k==0{return true;}
let mut prev=*s.pop_front().unwrap();
let mut k=k-1;
loop{
if k==0{return true;}
if k==1{let b=*s.pop_front().unwrap();return b>prev;}
let[b,c]=(*s.multi_pop_front::<2>().unwrap()).unbox();
if b<=prev||c<=b{return false;}
prev=c;
k-=2;
}
}
/// True when every byte left in `s` is zero.
fn aai(s:Span<u8>)->bool{
let mut s=s;
while let Some(c)=s.multi_pop_front::<8>(){
let[a,b,c,d,e,f,g,h]=(*c).unbox();
let t:ZF=a.into()+b.into()+c.into()+d.into()+e.into()+f.into()+g.into()+h.into();
if t!=0{return false;}
};
for b in s{if *b!=0{return false;}};
true
}
const T8:u128=42618535191663525756665312868166664448;
#[inline(always)]
pub(crate)fn kac(a:ZB<0,0xffffffffff>,xh:u128,sig:Span<ZF>)->Option<Array<u8>>{
let mut out:Array<u8>=array![];
let n8:NonZero<ZU<0x100>>=0x100;
let(a,b)=aaa::<_,_,4294967295,255>(a,n8);out.p(zu(b));
let(a,b)=aaa::<_,_,16777215,255>(a,n8);out.p(zu(b));
let(a,b)=aaa::<_,_,65535,255>(a,n8);out.p(zu(b));
let(a,b)=aaa::<_,_,255,255>(a,n8);out.p(zu(b));
out.p(zu(a));
if !kah(xh,n8,ref out){return None;}
let mut sg=sig;let[s76,s77,s78]=(*sg.multi_pop_back::<3>().unwrap()).unbox();
let x:u256=s76.into();
if !sai(x.low,n8,ref out)||!kah(x.high,n8,ref out){return None;}
let x:u256=s77.into();
if !sai(x.low,n8,ref out)||!kah(x.high,n8,ref out){return None;}
let x:u256=s78.into();
if x.high !=0{return None;}
let(q,b)=aaa::<_,_,1329227995784915872903807060280344575,255>(x.low,n8);out.p(zu(b));
match constrain::<ZB<0,1329227995784915872903807060280344575>,0x100>(q){Ok(b)=>{out.p(zu(b));},Err(_)=>{return None;}}
Some(out)
}
impl RM of ZD<u128,ZU<0x10000000000000000000000>>{type DivT=ZB<0,0xffffffffff>;type RemT=ZB<0,0xffffffffffffffffffffff>;}
impl CB of ConstrainHelper<ZB<0,1329227995784915872903807060280344575>,0x100>{type LowT=ZB<0,0xff>;type HighT=ZB<0x100,1329227995784915872903807060280344575>;}
#[inline(never)]
fn sai(v:u128,n8:NonZero<ZU<0x100>>,ref out:Array<u8>)->bool{
let(v,b)=aaa::<_,_,1329227995784915872903807060280344575,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,5192296858534827628530496329220095,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,20282409603651670423947251286015,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,79228162514264337593543950335,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,309485009821345068724781055,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,1208925819614629174706175,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,4722366482869645213695,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,18446744073709551615,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,72057594037927935,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,281474976710655,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,1099511627775,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,4294967295,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,16777215,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,65535,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,255,255>(v,n8);out.p(zu(b));
out.p(zu(v));
true
}
#[inline(never)]
fn kah(v:u128,n8:NonZero<ZU<0x100>>,ref out:Array<u8>)->bool{
let(v,b)=aaa::<_,_,1329227995784915872903807060280344575,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,5192296858534827628530496329220095,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,20282409603651670423947251286015,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,79228162514264337593543950335,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,309485009821345068724781055,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,1208925819614629174706175,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,4722366482869645213695,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,18446744073709551615,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,72057594037927935,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,281474976710655,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,1099511627775,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,4294967295,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,16777215,255>(v,n8);out.p(zu(b));
let(v,b)=aaa::<_,_,65535,255>(v,n8);out.p(zu(b));
match constrain::<_,256,th::C<_,256,255,65535>>(v){Ok(b)=>{out.p(zu(b));true},Err(_)=>false}
}
impl HG of ZD<crate::nttu::Ya,ZU<190464>>{type DivT=ZB<0,44>;type RemT=ZB<0,190463>;}
const Vm:NonZero<ZU<190464>>=190464;
#[inline(always)]
fn hq(u:crate::nttu::Ya,n2g:NonZero<ZU<190464>>)->ZF{
let(quotient,_)=zq::div_rem(u,n2g);
zu(quotient)
}
#[inline(always)]
fn hb(u:crate::nttu::Ya,n2g:NonZero<ZU<190464>>)->ZF{
let q=hq(u,n2g);
if q==44{
0
}else{
q
}
}
impl SM of ZD<u128,ZU<0x40000>>{
type DivT=ZB<0,0x3fffffffffffffffffffffffffff>;
type RemT=ZB<0,0x3ffff>;
}
const Tm:NonZero<ZU<0x40000>>=0x40000;
type U64=ZB<0,0xffffffffffffffff>;
impl TM of ZD<u128,ZU<0x10000000000000000>>{
type DivT=U64;
type RemT=U64;
}
const Qo:NonZero<ZU<0x10000000000000000>>=0x10000000000000000;
const Zx:NonZero<ZU<0x100000000>>=0x100000000;
const Py:ZU<0x100000000>=0x100000000;
impl VM of ConstrainHelper<U64,0x100000000000000>{
type LowT=ZB<0,0xffffffffffffff>;
type HighT=ZB<0x100000000000000,0xffffffffffffffff>;
}
impl WM of ConstrainHelper<U64,0x10000>{
type LowT=ZB<0,0xffff>;
type HighT=ZB<0x10000,0xffffffffffffffff>;
}
#[inline(always)]
pub fn lah(pk:Span<ZF>)->Option<Array<U64>>{if pk.len()!=43{return None;}let mut out:Array<U64>=array![];let mut ia=pk;while let Some(g)=ia.multi_pop_front::<8>(){let[f0,f1,f2,f3,f4,f5,f6,f7]=(*g).unbox();let x:u256=f0.into();let(a,r)=d64::<_,0xffffffffffffffff>(x.low);out.p(r);out.p(a);let(a,r)=d64::<_,0xffffffffffffffff>(x.high);out.p(r);let c=match constrain::<_,72057594037927936,th::C<_,72057594037927936,0xffffffffffffff,0xffffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f1.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(x.low,Q8);out.p(jn::<_,_,0xff00000000000000,_>(c,r,Wm));let(a,r)=d64::<_,0xffffffffffffff>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(x.high,Q8);out.p(jn::<_,_,0xff00000000000000,_>(c,r,Wm));let(a,r)=d64::<_,0xffffffffffffff>(a);out.p(r);let c=match constrain::<_,281474976710656,th::C<_,281474976710656,0xffffffffffff,0xffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f2.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(x.low,Yj);out.p(jn::<_,_,0xffff000000000000,_>(c,r,Ro));let(a,r)=d64::<_,0xffffffffffff>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(x.high,Yj);out.p(jn::<_,_,0xffff000000000000,_>(c,r,Ro));let(a,r)=d64::<_,0xffffffffffff>(a);out.p(r);let c=match constrain::<_,1099511627776,th::C<_,1099511627776,0xffffffffff,0xffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f3.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffff,16777215>(x.low,Xm);out.p(jn::<_,_,0xffffff0000000000,_>(c,r,Us));let(a,r)=d64::<_,0xffffffffff>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffff,16777215>(x.high,Xm);out.p(jn::<_,_,0xffffff0000000000,_>(c,r,Us));let(a,r)=d64::<_,0xffffffffff>(a);out.p(r);let c=match constrain::<_,4294967296,th::C<_,4294967296,4294967295,0xffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f4.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffffff,4294967295>(x.low,Q32);out.p(jn::<_,_,0xffffffff00000000,_>(c,r,Vs));let(a,r)=d64::<_,4294967295>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffffff,4294967295>(x.high,Q32);out.p(jn::<_,_,0xffffffff00000000,_>(c,r,Vs));let(a,r)=d64::<_,4294967295>(a);out.p(r);let c=match constrain::<_,16777216,th::C<_,16777216,16777215,4294967295>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f5.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffff,0xffffffffff>(x.low,Xl);out.p(jn::<_,_,0xffffffffff000000,_>(c,r,Ws));let(a,r)=d64::<_,16777215>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffff,0xffffffffff>(x.high,Xl);out.p(jn::<_,_,0xffffffffff000000,_>(c,r,Ws));let(a,r)=d64::<_,16777215>(a);out.p(r);let c=match constrain::<_,65536,th::C<_,65536,65535,16777215>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f6.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffff,0xffffffffffff>(x.low,Ym);out.p(jn::<_,_,0xffffffffffff0000,_>(c,r,Xs));let(a,r)=d64::<_,65535>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffff,0xffffffffffff>(x.high,Ym);out.p(jn::<_,_,0xffffffffffff0000,_>(c,r,Xs));let(a,r)=d64::<_,65535>(a);out.p(r);let c=match constrain::<_,256,th::C<_,256,255,65535>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f7.into();let(a,r)=aaa::<_,_,0xffffffffffffffffff,0xffffffffffffff>(x.low,Ys);out.p(jn::<_,_,0xffffffffffffff00,_>(c,r,W8));let(a,r)=d64::<_,255>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffff,0xffffffffffffff>(x.high,Ys);out.p(jn::<_,_,0xffffffffffffff00,_>(c,r,W8));let r=match constrain::<_,0x10000000000000000,th::C<_,0x10000000000000000,0xffffffffffffffff,0xffffffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};out.p(r);}let[f0,f1,f2]=(*ia.multi_pop_front::<3>().unwrap()).unbox();let x:u256=f0.into();let(a,r)=d64::<_,0xffffffffffffffff>(x.low);out.p(r);out.p(a);let(a,r)=d64::<_,0xffffffffffffffff>(x.high);out.p(r);let c=match constrain::<_,72057594037927936,th::C<_,72057594037927936,0xffffffffffffff,0xffffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f1.into();let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(x.low,Q8);out.p(jn::<_,_,0xff00000000000000,_>(c,r,Wm));let(a,r)=d64::<_,0xffffffffffffff>(a);out.p(r);let c=a;let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffffff,255>(x.high,Q8);out.p(jn::<_,_,0xff00000000000000,_>(c,r,Wm));let(a,r)=d64::<_,0xffffffffffffff>(a);out.p(r);let c=match constrain::<_,281474976710656,th::C<_,281474976710656,0xffffffffffff,0xffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};let x:u256=f2.into();if x.high!=0{return None;}let(a,r)=aaa::<_,_,0xffffffffffffffffffffffffffff,65535>(x.low,Yj);out.p(jn::<_,_,0xffff000000000000,_>(c,r,Ro));let r=match constrain::<_,0x10000000000000000,th::C<_,0x10000000000000000,0xffffffffffffffff,0xffffffffffffffffffffffffffff>>(a){Ok(v)=>v,Err(_)=>{return None;}};out.p(r);Some(out)}const Q8:NonZero<ZU<256>>=256;const Yj:NonZero<ZU<65536>>=65536;const Xm:NonZero<ZU<16777216>>=16777216;const Q32:NonZero<ZU<4294967296>>=4294967296;const Xl:NonZero<ZU<1099511627776>>=1099511627776;const Ym:NonZero<ZU<281474976710656>>=281474976710656;const Ys:NonZero<ZU<72057594037927936>>=72057594037927936;const Q64:NonZero<ZU<18446744073709551616>>=18446744073709551616;const W8:ZU<256>=256;const Xs:ZU<65536>=65536;const Ws:ZU<16777216>=16777216;const Vs:ZU<4294967296>=4294967296;const Us:ZU<1099511627776>=1099511627776;const Ro:ZU<281474976710656>=281474976710656;const Wm:ZU<72057594037927936>=72057594037927936;
pub(crate) mod th{
pub impl A<L,R,const LO:felt252,const HI:felt252>of super::AddHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
pub impl M<L,R,const LO:felt252,const HI:felt252>of super::MulHelper<L,R>{
type Result=super::ZB<LO,HI>;
}
pub impl D<L,R,const QH:felt252,const RH:felt252>of super::ZD<L,R>{
type DivT=super::ZB<0,QH>;
type RemT=super::ZB<0,RH>;
}
pub impl C<T,const B:felt252,const LH:felt252,const HH:felt252>of super::ConstrainHelper<T,B>{type LowT=super::ZB<0,LH>;type HighT=super::ZB<B,HH>;}
}
#[inline(always)]
pub(crate) fn gaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::add::<L,R,th::A<L,R,LO,HI>>(l,r)
}
#[inline(always)]
pub(crate) fn kaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{
zq::mul::<L,R,th::M<L,R,LO,HI>>(l,r)
}
#[inline(always)]
fn aaa<L,R,const QH:ZF,const RH:ZF>(l:L,r:NonZero<R>)->(ZB<0,QH>,ZB<0,RH>){
zq::div_rem::<L,R,th::D<L,R,QH,RH>>(l,r)
}
#[inline(always)]
fn f32(ref s:Span<U64>,n10:NonZero<ZU<0x400>>)->(ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF){
let[x0,x1,x2,x3,x4]=(*s.multi_pop_front::<5>().unwrap()).unbox();
let a=x0;
let(a,c0)=aaa::<_,_,18014398509481983,1023>(a,n10);
let(a,c1)=aaa::<_,_,17592186044415,1023>(a,n10);
let(a,c2)=aaa::<_,_,17179869183,1023>(a,n10);
let(a,c3)=aaa::<_,_,16777215,1023>(a,n10);
let(a,c4)=aaa::<_,_,16383,1023>(a,n10);
let(a,c5)=aaa::<_,_,15,1023>(a,n10);
let a=gaa::<_,_,0,295147905179352825855>(a,kaa::<_,_,0,295147905179352825840>(x1,Qy));
let(a,c6)=aaa::<_,_,288230376151711743,1023>(a,n10);
let(a,c7)=aaa::<_,_,281474976710655,1023>(a,n10);
let(a,c8)=aaa::<_,_,274877906943,1023>(a,n10);
let(a,c9)=aaa::<_,_,268435455,1023>(a,n10);
let(a,c10)=aaa::<_,_,262143,1023>(a,n10);
let(a,c11)=aaa::<_,_,255,1023>(a,n10);
let a=gaa::<_,_,0,4722366482869645213695>(a,kaa::<_,_,0,4722366482869645213440>(x2,Rs));
let(a,c12)=aaa::<_,_,4611686018427387903,1023>(a,n10);
let(a,c13)=aaa::<_,_,4503599627370495,1023>(a,n10);
let(a,c14)=aaa::<_,_,4398046511103,1023>(a,n10);
let(a,c15)=aaa::<_,_,4294967295,1023>(a,n10);
let(a,c16)=aaa::<_,_,4194303,1023>(a,n10);
let(a,c17)=aaa::<_,_,4095,1023>(a,n10);
let(a,c18)=aaa::<_,_,3,1023>(a,n10);
let a=gaa::<_,_,0,73786976294838206463>(a,kaa::<_,_,0,73786976294838206460>(x3,XB));
let(a,c19)=aaa::<_,_,72057594037927935,1023>(a,n10);
let(a,c20)=aaa::<_,_,70368744177663,1023>(a,n10);
let(a,c21)=aaa::<_,_,68719476735,1023>(a,n10);
let(a,c22)=aaa::<_,_,67108863,1023>(a,n10);
let(a,c23)=aaa::<_,_,65535,1023>(a,n10);
let(a,c24)=aaa::<_,_,63,1023>(a,n10);
let a=gaa::<_,_,0,1180591620717411303423>(a,kaa::<_,_,0,1180591620717411303360>(x4,Ry));
let(a,c25)=aaa::<_,_,1152921504606846975,1023>(a,n10);
let(a,c26)=aaa::<_,_,1125899906842623,1023>(a,n10);
let(a,c27)=aaa::<_,_,1099511627775,1023>(a,n10);
let(a,c28)=aaa::<_,_,1073741823,1023>(a,n10);
let(a,c29)=aaa::<_,_,1048575,1023>(a,n10);
let(a,c30)=aaa::<_,_,1023,1023>(a,n10);
let c31=a;
(zu(c0),zu(c1),zu(c2),zu(c3),zu(c4),zu(c5),zu(c6),zu(c7),zu(c8),zu(c9),zu(c10),zu(c11),zu(c12),zu(c13),zu(c14),zu(c15),zu(c16),zu(c17),zu(c18),zu(c19),zu(c20),zu(c21),zu(c22),zu(c23),zu(c24),zu(c25),zu(c26),zu(c27),zu(c28),zu(c29),zu(c30),zu(c31))
}
const Yl:NonZero<ZU<0x400>>=0x400;
const Qy:ZU<16>=16;
const Rs:ZU<256>=256;
const XB:ZU<4>=4;
const Ry:ZU<64>=64;
#[derive(Copy,Drop)]
struct So{f0:Span<U64>,f1:Span<U64>,f2:Span<U64>,f3:Span<U64>,f4:Span<U64>,f5:Span<U64>,f6:Span<U64>,f7:Span<U64>}
#[inline(always)]pub fn cac(lanes:Span<U64>)->Array<ZF>{
let s0=lanes.slice(4,20);
let s1=lanes.slice(24,20);
let s2=lanes.slice(44,20);
let s3=lanes.slice(64,20);
let s4=lanes.slice(84,20);
let s5=lanes.slice(104,20);
let s6=lanes.slice(124,20);
let s7=lanes.slice(144,20);
let mut f:Array<ZF>=array![];
let mut y:Array<ZF>=array![];
let n10:NonZero<ZU<0x400>>=Yl;
let mut it:u32=0;
let eaa:ZF=0x200000000000000000000000000000000000;let s13:ZF=0x2000;
let ia:ZF=-0x200000000000000000000000000000000000;
let p18:ZF=0x80000000;
let p36:ZF=0x4000000000000000;
let p54:ZF=0x200000000000000000000000;
let mut oa=So{f0:s0,f1:s1,f2:s2,f3:s3,f4:s4,f5:s5,f6:s6,f7:s7};
while it !=4{let So{f0:ib,f1:ob,f2:ic,f3:oc,f4:od,f5:ie,f6:oe,f7:ag}=oa;let mut s0=ib;let mut s1=ob;let mut s2=ic;let mut s3=oc;let mut s4=od;let mut s5=ie;let mut s6=oe;let mut s7=ag;
let(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,a11,a12,a13,a14,a15,a16,a17,a18,a19,a20,a21,a22,a23,a24,a25,a26,a27,a28,a29,a30,a31)=f32(ref s0,n10);
let(b0,b1,b2,b3,b4,b5,b6,b7,b8,b9,b10,b11,b12,b13,b14,b15,b16,b17,b18,b19,b20,b21,b22,b23,b24,b25,b26,b27,b28,b29,b30,b31)=f32(ref s1,n10);
let(c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15,c16,c17,c18,c19,c20,c21,c22,c23,c24,c25,c26,c27,c28,c29,c30,c31)=f32(ref s2,n10);
let(d0,d1,d2,d3,d4,d5,d6,d7,d8,d9,bg,cg,dg,eg,fg,gg,hg,ig,jg,kg,lg,mg,ng,og,pg,qg,rg,tg,ug,vg,wg,xg)=f32(ref s3,n10);
let(e0,e1,e2,e3,e4,e5,e6,e7,e8,e9,e10,e11,e12,e13,e14,e15,e16,e17,e18,e19,e20,e21,e22,e23,e24,yg,zg,bh,ch,dh,eh,gh)=f32(ref s4,n10);
let(f0,f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,f21,f22,f23,f24,f25,f26,f27,f28,f29,f30,f31)=f32(ref s5,n10);
let(g0,g1,g2,g3,g4,g5,g6,g7,g8,g9,ih,kh,lh,nh,oh,ph,rh,sh,uh,vh,wh,yh,zh,ci,di,ii,ji,ki,mi,ni,oi,pi)=f32(ref s6,n10);
let(h0,h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23,h24,qi,ri,si,ti,ui,vi,wi)=f32(ref s7,n10);
let lo=a0+p18*c0+p36*e0+p54*g0;
let hi=b0+p18*d0+p36*f0+p54*h0;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a1+p18*c1+p36*e1+p54*g1;
let hi=b1+p18*d1+p36*f1+p54*h1;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a2+p18*c2+p36*e2+p54*g2;
let hi=b2+p18*d2+p36*f2+p54*h2;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a3+p18*c3+p36*e3+p54*g3;
let hi=b3+p18*d3+p36*f3+p54*h3;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a4+p18*c4+p36*e4+p54*g4;
let hi=b4+p18*d4+p36*f4+p54*h4;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a5+p18*c5+p36*e5+p54*g5;
let hi=b5+p18*d5+p36*f5+p54*h5;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a6+p18*c6+p36*e6+p54*g6;
let hi=b6+p18*d6+p36*f6+p54*h6;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a7+p18*c7+p36*e7+p54*g7;
let hi=b7+p18*d7+p36*f7+p54*h7;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a8+p18*c8+p36*e8+p54*g8;
let hi=b8+p18*d8+p36*f8+p54*h8;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a9+p18*c9+p36*e9+p54*g9;
let hi=b9+p18*d9+p36*f9+p54*h9;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a10+p18*c10+p36*e10+p54*ih;
let hi=b10+p18*bg+p36*f10+p54*h10;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a11+p18*c11+p36*e11+p54*kh;
let hi=b11+p18*cg+p36*f11+p54*h11;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a12+p18*c12+p36*e12+p54*lh;
let hi=b12+p18*dg+p36*f12+p54*h12;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a13+p18*c13+p36*e13+p54*nh;
let hi=b13+p18*eg+p36*f13+p54*h13;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a14+p18*c14+p36*e14+p54*oh;
let hi=b14+p18*fg+p36*f14+p54*h14;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a15+p18*c15+p36*e15+p54*ph;
let hi=b15+p18*gg+p36*f15+p54*h15;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a16+p18*c16+p36*e16+p54*rh;
let hi=b16+p18*hg+p36*f16+p54*h16;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a17+p18*c17+p36*e17+p54*sh;
let hi=b17+p18*ig+p36*f17+p54*h17;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a18+p18*c18+p36*e18+p54*uh;
let hi=b18+p18*jg+p36*f18+p54*h18;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a19+p18*c19+p36*e19+p54*vh;
let hi=b19+p18*kg+p36*f19+p54*h19;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a20+p18*c20+p36*e20+p54*wh;
let hi=b20+p18*lg+p36*f20+p54*h20;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a21+p18*c21+p36*e21+p54*yh;
let hi=b21+p18*mg+p36*f21+p54*h21;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a22+p18*c22+p36*e22+p54*zh;
let hi=b22+p18*ng+p36*f22+p54*h22;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a23+p18*c23+p36*e23+p54*ci;
let hi=b23+p18*og+p36*f23+p54*h23;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a24+p18*c24+p36*e24+p54*di;
let hi=b24+p18*pg+p36*f24+p54*h24;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a25+p18*c25+p36*yg+p54*ii;
let hi=b25+p18*qg+p36*f25+p54*qi;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a26+p18*c26+p36*zg+p54*ji;
let hi=b26+p18*rg+p36*f26+p54*ri;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a27+p18*c27+p36*bh+p54*ki;
let hi=b27+p18*tg+p36*f27+p54*si;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a28+p18*c28+p36*ch+p54*mi;
let hi=b28+p18*ug+p36*f28+p54*ti;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a29+p18*c29+p36*dh+p54*ni;
let hi=b29+p18*vg+p36*f29+p54*ui;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a30+p18*c30+p36*eh+p54*oi;
let hi=b30+p18*wg+p36*f30+p54*vi;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
let lo=a31+p18*c31+p36*gh+p54*pi;
let hi=b31+p18*xg+p36*f31+p54*wi;
f.p(ia*hi-s13*lo);
y.p(s13*hi-eaa*lo);
it+=1;
oa=So{f0:s0,f1:s1,f2:s2,f3:s3,f4:s4,f5:s5,f6:s6,f7:s7};
}
crate::ct::hac(ref f,y.span(),-1);
let fx=f.span().slice(0,128);
crate::ct::hac(ref f,fx,-1);
crate::ct::qab(ref f,y.span());
crate::ct::qab(ref f,fx);
f
}
impl Sy of ConstrainHelper<ZB<0,190463>,95232>{
type LowT=ZB<0,95231>;
type HighT=ZB<95232,190463>;
}
#[inline(always)]
fn saa(u:crate::nttu::Ya)->ZF{
let(quotient,rem)=zq::div_rem(u,Vm);
let q:ZF=zu(quotient);
match constrain::<ZB<0,190463>,95232>(rem){
Ok(_)=>{if q*(q-44)==0{43}else{-1}},
Err(_)=>{if q==43{-43}else{1}},
}
}
const Qm:[ZF;16]=[
0x1,0x40,0x1000,0x40000,0x1000000,0x40000000,0x1000000000,0x40000000000,
0x1000000000000,0x40000000000000,0x1000000000000000,0x40000000000000000,
0x1000000000000000000,0x40000000000000000000,0x1000000000000000000000,
0x40000000000000000000000,
];
#[inline(never)]
fn aad(g:@Box<[crate::nttu::Ya;32]>)->(ZF,ZF){
let n2g:NonZero<ZU<190464>>=Vm;
let[u0,u1,u2,u3,u4,u5,u6,u7,u8,u9,u10,u11,u12,u13,u14,u15,u16,u17,u18,u19,u20,u21,u22,u23,u24,u25,u26,u27,u28,u29,u30,u31]=(*g).unbox();
let rab:ZF=hb(u0,n2g)
+0x40*hb(u1,n2g)
+0x1000*hb(u2,n2g)
+0x40000*hb(u3,n2g)
+0x1000000*hb(u4,n2g)
+0x40000000*hb(u5,n2g)
+0x1000000000*hb(u6,n2g)
+0x40000000000*hb(u7,n2g)
+0x1000000000000*hb(u8,n2g)
+0x40000000000000*hb(u9,n2g)
+0x1000000000000000*hb(u10,n2g)
+0x40000000000000000*hb(u11,n2g)
+0x1000000000000000000*hb(u12,n2g)
+0x40000000000000000000*hb(u13,n2g)
+0x1000000000000000000000*hb(u14,n2g)
+0x40000000000000000000000*hb(u15,n2g);
let sab:ZF=hb(u16,n2g)
+0x40*hb(u17,n2g)
+0x1000*hb(u18,n2g)
+0x40000*hb(u19,n2g)
+0x1000000*hb(u20,n2g)
+0x40000000*hb(u21,n2g)
+0x1000000000*hb(u22,n2g)
+0x40000000000*hb(u23,n2g)
+0x1000000000000*hb(u24,n2g)
+0x40000000000000*hb(u25,n2g)
+0x1000000000000000*hb(u26,n2g)
+0x40000000000000000*hb(u27,n2g)
+0x1000000000000000000*hb(u28,n2g)
+0x40000000000000000000*hb(u29,n2g)
+0x1000000000000000000000*hb(u30,n2g)
+0x40000000000000000000000*hb(u31,n2g);
(rab,sab)
}
pub(crate)fn zaa(w:Span<crate::nttu::Ya>,positions:Span<u8>,ref out:Array<u64>){
let mut rest=positions;
let mut next:u32=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
let mut n:u32=0;
let mut ws=w;
let sl=Qm.span();
let n2g:NonZero<ZU<190464>>=Vm;
while let Some(g)=ws.multi_pop_front::<32>(){
let[u0,u1,u2,u3,u4,u5,u6,u7,u8,u9,u10,u11,u12,u13,u14,u15,u16,u17,u18,u19,u20,u21,u22,u23,u24,u25,u26,u27,u28,u29,u30,u31]=(*g).unbox();
let q0=hq(u0,n2g);let q1=hq(u1,n2g);let q2=hq(u2,n2g);let q3=hq(u3,n2g);
let q4=hq(u4,n2g);let q5=hq(u5,n2g);let q6=hq(u6,n2g);let q7=hq(u7,n2g);
let q8=hq(u8,n2g);let q9=hq(u9,n2g);let q10=hq(u10,n2g);let q11=hq(u11,n2g);
let q12=hq(u12,n2g);let q13=hq(u13,n2g);let q14=hq(u14,n2g);let q15=hq(u15,n2g);
let q16=hq(u16,n2g);let q17=hq(u17,n2g);let q18=hq(u18,n2g);let q19=hq(u19,n2g);
let q20=hq(u20,n2g);let q21=hq(u21,n2g);let q22=hq(u22,n2g);let q23=hq(u23,n2g);
let q24=hq(u24,n2g);let q25=hq(u25,n2g);let q26=hq(u26,n2g);let q27=hq(u27,n2g);
let q28=hq(u28,n2g);let q29=hq(u29,n2g);let q30=hq(u30,n2g);let q31=hq(u31,n2g);
let bad=(q0-44)*(q1-44)*(q2-44)*(q3-44)*(q4-44)*(q5-44)*(q6-44)*(q7-44)
*(q8-44)*(q9-44)*(q10-44)*(q11-44)*(q12-44)*(q13-44)*(q14-44)*(q15-44)
*(q16-44)*(q17-44)*(q18-44)*(q19-44)*(q20-44)*(q21-44)*(q22-44)*(q23-44)
*(q24-44)*(q25-44)*(q26-44)*(q27-44)*(q28-44)*(q29-44)*(q30-44)*(q31-44);
let(mut rab,mut sab)=if bad==0{
aad(g)
}else{
(
q0+0x40*q1+0x1000*q2+0x40000*q3+0x1000000*q4+0x40000000*q5
+0x1000000000*q6+0x40000000000*q7+0x1000000000000*q8
+0x40000000000000*q9+0x1000000000000000*q10+0x40000000000000000*q11
+0x1000000000000000000*q12+0x40000000000000000000*q13
+0x1000000000000000000000*q14+0x40000000000000000000000*q15,
q16+0x40*q17+0x1000*q18+0x40000*q19+0x1000000*q20+0x40000000*q21
+0x1000000000*q22+0x40000000000*q23+0x1000000000000*q24
+0x40000000000000*q25+0x1000000000000000*q26+0x40000000000000000*q27
+0x1000000000000000000*q28+0x40000000000000000000*q29
+0x1000000000000000000000*q30+0x40000000000000000000000*q31,
)
};
n+=32;
while next<n{
let k=next+32-n;
if k<16{
rab+=saa(*w.at(next))**sl.at(k);
}else{
sab+=saa(*w.at(next))**sl.at(k-16);
}
next=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
if next>=n{break;}
let k=next+32-n;
if k<16{
rab+=saa(*w.at(next))**sl.at(k);
}else{
sab+=saa(*w.at(next))**sl.at(k-16);
}
next=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
if next>=n{break;}
let k=next+32-n;
if k<16{
rab+=saa(*w.at(next))**sl.at(k);
}else{
sab+=saa(*w.at(next))**sl.at(k-16);
}
next=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
if next>=n{break;}
let k=next+32-n;
if k<16{
rab+=saa(*w.at(next))**Qm.span().at(k);
}else{
sab+=saa(*w.at(next))**Qm.span().at(k-16);
}
next=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
}
let l:ZB<0,0xffffffffffffffffffffffff>=downcast(rab).unwrap();
let u:ZB<0,0xffffffffffffffffffffffff>=downcast(sab).unwrap();
let(a,b)=aaa::<_,_,0xffffffff,0xffffffffffffffff>(l,Qo);
let(c,d)=aaa::<_,_,0xffffffffffffffff,0xffffffff>(u,Zx);
let ia=gaa::<_,_,0,0xffffffffffffffff>(a,kaa::<_,_,0,0xffffffff00000000>(d,Py));
out.p(zu(b));out.p(zu(ia));out.p(zu(c));
}
}
impl Pn of ConstrainHelper<ZB<0,190463>,95233>{
type LowT=ZB<0,95232>;
type HighT=ZB<95233,190463>;
}
#[inline(always)]
fn waa(u:crate::nttu::Ya)->ZF{
let(quotient,rem)=zq::div_rem(u,Vm);
let q:ZF=zu(quotient);
match constrain::<ZB<0,190463>,95233>(rem){
Ok(r)=>{
if zu::<_,ZF>(r)==0{
if q==0{43}else if q==44{-43}else{1}
}else if q==0{43}else{-1}
},
Err(_)=>{if q==43{-43}else{1}},
}
}
const UM:ZU<11545610>=11545610;
const Zs:ZU<281474976710656>=281474976710656;
pub(crate) const Qs:u128=0x7e00000000007e0000000000;
pub(crate) const Uz:ZF=0x7fffffffffc0010fffffffff780000000000000000000000000000000000001;
pub(crate) const Vz:ZF=0x7c0000000000010780000000000000000000000000000000000000000000001;
#[inline(always)]
fn ia(a:crate::nttu::Ya,b:crate::nttu::Ya,c:ZF,hm:u128)->ZF{
let pb=kaa::<_,_,0,2358877398425608912896>(b,Zs);
let s=gaa::<_,_,0,2358877398425617293312>(a,pb);
let x=kaa::<_,_,0,27234678480036791277835960320>(s,UM);
let y:u128=zu(x)&hm;
let yf:ZF=y.into();
yf*c
}
/// hpair without the slot multiplier: the residue pair is pre-shifted by K/UM, so a group of pairs sums in place.
#[inline]
pub(crate) fn hp<T,const B:ZF,+Drop<T>>(a:crate::nttu::Ya,b:crate::nttu::Ya,k:T,hm:u128)->ZF{
let pb=kaa::<_,_,0,2358877398425608912896>(b,Zs);
let s=gaa::<_,_,0,2358877398425617293312>(a,pb);
let x=kaa::<_,_,0,B>(s,k);
let y:u128=zu(x)&hm;
y.into()
}
pub(crate) const K0:ZU<11545610>=11545610;pub(crate) const B0:ZF=27234678480036791277835960320;pub(crate) const K1:ZU<738919040>=738919040;pub(crate) const B1:ZF=1743019422722354641781501460480;pub(crate) const K2:ZU<47290818560>=47290818560;pub(crate) const B2:ZF=111553243054230697074016093470720;pub(crate) const K3:ZU<3026612387840>=3026612387840;pub(crate) const B3:ZF=7139407555470764612737029982126080;pub(crate) const K4:ZU<193703192821760>=193703192821760;pub(crate) const B4:ZF=456922083550128935215169918856069120;pub(crate) const K5:ZU<12397004340592640>=12397004340592640;pub(crate) const B5:ZF=29243013347208251853770874806788423680;const YB:u128=0x1f80000000001f800000000000;const PC:u128=0x7e00000000007e0000000000000;const QC:u128=0x1f80000000001f800000000000000;const RC:u128=0x7e00000000007e0000000000000000;const SC:u128=0x1f80000000001f800000000000000000;
#[inline(never)]
pub(crate) fn rai()->(u128,u128,u128,u128,u128){(YB,PC,QC,RC,SC)}
pub(crate) const Wz:ZF=0x80000000000000;
pub(crate) const Xz:ZF=0x80000000000000000000000;
const Uo:[ZF;32]=[
0x1,
0x40,
0x1000,
0x40000,
0x1000000,
0x40000000,
0x1000000000,
0x40000000000,
0x1000000000000,
0x40000000000000,
0x1000000000000000,
0x40000000000000000,
0x1000000000000000000,
0x40000000000000000000,
0x1000000000000000000000,
0x40000000000000000000000,
0x1000000000000000000000000,
0x40000000000000000000000000,
0x1000000000000000000000000000,
0x40000000000000000000000000000,
0x1000000000000000000000000000000,
0x40000000000000000000000000000000,
0x1000000000000000000000000000000000,
0x40000000000000000000000000000000000,
0x1000000000000000000000000000000000000,
0x40000000000000000000000000000000000000,
0x1000000000000000000000000000000000000000,
0x40000000000000000000000000000000000000000,
0x1000000000000000000000000000000000000000000,
0x40000000000000000000000000000000000000000000,
0x1000000000000000000000000000000000000000000000,
0x40000000000000000000000000000000000000000000000,
];
/// Applies the hints of one 32-coefficient block to its packed HighBits word `l` and appends its three w1 words.
#[inline(always)]
fn hbl(l:ZF,w:Span<crate::nttu::Ya>,sl:Span<ZF>,n64:NonZero<ZU<0x10000000000000000>>,ref next:u32,ref rest:Span<u8>,ref base:u32,ref out:Array<u64>){
let mut l=l;
if let Some(s)=sl.get(next-base){
l+=waa(*w.at(next))**s.unbox();
match rest.pop_front(){Some(p)=>{next=(*p).into();if let Some(s)=sl.get(next-base){
let mut s=s;
loop{
l+=waa(*w.at(next))**s.unbox();
match rest.pop_front(){Some(p)=>{next=(*p).into();match sl.get(next-base){Some(t)=>{s=t;},None=>{break;}}},None=>{next=256;break;}}
l+=waa(*w.at(next))**s.unbox();
match rest.pop_front(){Some(p)=>{next=(*p).into();match sl.get(next-base){Some(t)=>{s=t;},None=>{break;}}},None=>{next=256;break;}}
};
}},None=>{next=256;}}
}
base+=32;
let v:u256=l.into();
let(w1,w0)=zq::div_rem(v.low,n64);
let w2:u64=v.high.try_into().unwrap();
out.p(zu(w0));out.p(zu(w1));out.p(w2);
}
/// UseHint for one row from the packed block words computed inside intt_row: hints are applied in coefficient
/// order and each block emits three w1 words.
pub(crate)fn eab(ls:(ZF,ZF,ZF,ZF,ZF,ZF,ZF,ZF),w:Span<crate::nttu::Ya>,positions:Span<u8>,ref out:Array<u64>){
let mut rest=positions;
let mut next:u32=match rest.pop_front(){Some(p)=>(*p).into(),None=>256};
let mut base:u32=0;
let sl=Uo.span();
let n64:NonZero<ZU<0x10000000000000000>>=Qo;
let(l0,l1,l2,l3,l4,l5,l6,l7)=ls;
hbl(l0,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l1,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l2,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l3,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l4,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l5,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l6,w,sl,n64,ref next,ref rest,ref base,ref out);
hbl(l7,w,sl,n64,ref next,ref rest,ref base,ref out);
}

type ZF=felt252;
#[inline]fn jn<C,R,const M:ZF,W,+Drop<C>,+Drop<R>,+Drop<W>>(c:C,r:R,w:W)->U64{gaa::<_,_,0,0xffffffffffffffff>(c,kaa::<_,_,0,M>(r,w))}
#[inline]fn d64<T,const H:ZF,+Drop<T>>(a:T)->(ZB<0,H>,U64){aaa::<_,_,H,0xffffffffffffffff>(a,Q64)}
