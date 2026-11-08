use crate::k2::Ap;
use corelib_imports::bounded_int::{AddHelper,BoundedInt as ZB,DivRemHelper as ZD,MulHelper,UnitInt as ZU,bounded_int as zq,upcast as zu};
use core::internal::bounded_int::{ConstrainHelper,constrain};
use corelib_imports::integer::{U128sFromFelt252Result as R,u128s_from_felt252 as us};
mod th{pub impl D<L,R,const QH:felt252,const RH:felt252>of super::ZD<L,R>{type DivT=super::ZB<0,QH>;type RemT=super::ZB<0,RH>;}pub impl A<L,R,const LO:felt252,const HI:felt252>of super::AddHelper<L,R>{type Result=super::ZB<LO,HI>;}pub impl M<L,R,const LO:felt252,const HI:felt252>of super::MulHelper<L,R>{type Result=super::ZB<LO,HI>;}pub impl C<T,const B:felt252,const LH:felt252,const HH:felt252>of super::ConstrainHelper<T,B>{type LowT=super::ZB<0,LH>;type HighT=super::ZB<B,HH>;}pub impl E<L,R,const QL:felt252,const QH:felt252,const RH:felt252>of super::ZD<L,R>{type DivT=super::ZB<QL,QH>;type RemT=super::ZB<0,RH>;}pub impl F<T,const B:felt252,const LL:felt252,const LH:felt252,const HH:felt252>of super::ConstrainHelper<T,B>{type LowT=super::ZB<LL,LH>;type HighT=super::ZB<B,HH>;}}
#[inline(always)]fn gaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{zq::add::<L,R,th::A<L,R,LO,HI>>(l,r)}
#[inline(always)]fn kaa<L,R,const LO:ZF,const HI:ZF>(l:L,r:R)->ZB<LO,HI>{zq::mul::<L,R,th::M<L,R,LO,HI>>(l,r)}
#[inline(always)]fn dv<T,const K:ZF,const QH:ZF,const RH:ZF>(a:T,n:NonZero<ZU<K>>)->(ZB<0,QH>,ZB<0,RH>){zq::div_rem::<T,ZU<K>,th::D<T,ZU<K>,QH,RH>>(a,n)}
#[inline(always)]fn cs<T,const B:ZF,const LH:ZF,const HH:ZF>(a:T)->Result<ZB<0,LH>,ZB<B,HH>>{constrain::<T,B,th::C<T,B,LH,HH>>(a)}
type Qg=ZB<0,262143>;
type Yd=ZB<0,262144>;
/// Output rule for one z coefficient: `make` takes a raw digit x (z = gamma1 - x), `make_o` a digit x' = x + 78 read from an offset chain.
trait Wi<O>{fn qaa(x:Yd,zc:ZU<131072>)->O;fn lac(x:Qg,zo:ZU<131150>)->O;}
impl SH of Wi<ZF>{#[inline(always)]fn qaa(x:Yd,zc:ZU<131072>)->ZF{8511489-zu::<_,ZF>(x)}#[inline(always)]fn lac(x:Qg,zo:ZU<131150>)->ZF{8511567-zu::<_,ZF>(x)}}
impl YK of zq::SubHelper<ZU<131072>,Yd>{type Result=ZB<-131072,131072>;}
impl UH of zq::SubHelper<ZU<131150>,Qg>{type Result=ZB<-130993,131150>;}
impl RD of Wi<crate::Z>{#[inline(always)]fn qaa(x:Yd,zc:ZU<131072>)->crate::Z{crate::Z{v:zu(zq::sub(zc,x))}}#[inline(always)]fn lac(x:Qg,zo:ZU<131150>)->crate::Z{crate::Z{v:zu(zq::sub(zo,x))}}}
#[inline]
fn tk<T,const QH:ZF,O,+Drop<O>,impl A:Wi<O>>(a:T,n18:NonZero<ZU<0x40000>>,zc:ZU<131072>,ref out:Array<O>)->(ZB<0,QH>,Yd){
let(q,c)=zq::div_rem::<T,ZU<0x40000>,th::D<T,ZU<0x40000>,QH,262143>>(a,n18);
out.p(A::qaa(zu(c),zc));
(q,zu(c))
}
/// Takes one digit from a chain value that carries the +78 per-digit offset; the remainder x' is emitted with `make_o`.
#[inline]
fn tko<T,const QL:ZF,const QH:ZF,O,+Drop<O>,impl A:Wi<O>>(a:T,n18:NonZero<ZU<0x40000>>,zo:ZU<131150>,ref out:Array<O>)->(ZB<QL,QH>,Yd){
let(q,c)=zq::div_rem::<T,ZU<0x40000>,th::E<T,ZU<0x40000>,QL,QH,262143>>(a,n18);
out.p(A::lac(c,zo));
(q,zu(c))
}
pub(crate)const Yi:u128=0x20000400008000100002000040000;
type WN=ZB<0,262143>;
type Sm=ZB<0,0xffffffffffffffffffffffffffffff>;
#[inline(never)]
fn gab<O,+Drop<O>,impl A:Wi<O>>(ref sig:Span<ZF>,a0:Sm,h0:u128,ok:u128,zc:ZU<131072>,zo:ZU<131150>,ref out:Array<O>)->(u128,Sm,u128){let[w1,w2,w3,w4,w5,w6,w7,w8,w9]=(*sig.multi_pop_front::<9>().unwrap()).unbox();let Ra=match us(w1){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Sa=match us(w2){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Ta=match us(w3){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Ua=match us(w4){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Va=match us(w5){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Wa=match us(w6){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Xa=match us(w7){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Rb=match us(w8){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let Sb=match us(w9){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let mut ok=ok;let n18=iad();
let a=gaa::<_,_,0x138004e00138004e00138004e,0x100000138004e00138004e00138004d>(a0,Tg);let(a,x1)=tko::<_,Q0,Q1,_>(a,n18,zo,ref out);let(a,x2)=tko::<_,Q2,Q3,_>(a,n18,zo,ref out);let(a,x3)=tko::<_,Q4,Q5,_>(a,n18,zo,ref out);let(a,x4)=tko::<_,20447310,Q6,_>(a,n18,zo,ref out);let(a,x5)=tko::<_,78,Q7,_>(a,n18,zo,ref out);let(a,x6)=tko::<_,0,4096,_>(a,n18,zo,ref out);ok=ok&g0(x1,x2,x3,x4,x5,x6);let c=a;let(a,r)=dv::<_,64,0x3ffffffffffffffffffffffffffffff,63>(h0,N6);let x7:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,258048>(r,Wp)));out.p(A::qaa(x7,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x400000138004e00138004e00138004d>(a,Tg);let(a,x8)=tko::<_,Q0,Q8,_>(a,n18,zo,ref out);let(a,x9)=tko::<_,Q2,Q9,_>(a,n18,zo,ref out);let(a,x10)=tko::<_,Q4,Xp,_>(a,n18,zo,ref out);let(a,x11)=tko::<_,20447310,Yp,_>(a,n18,zo,ref out);let(a,x12)=tko::<_,78,Pq,_>(a,n18,zo,ref out);let(a,x13)=tko::<_,0,16384,_>(a,n18,zo,ref out);ok=ok&g0(x8,x9,x10,x11,x12,x13);let c=match cs::<_,64,63,16384>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Ra;let(a,r)=dv::<_,4096,0xfffffffffffffffffffffffffffff,4095>(x.low,Qq);let x14:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,262080>(r,P6)));out.p(A::qaa(x14,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x10000138004e00138004e00138004d>(a,Tg);let(a,x15)=tko::<_,Q0,Rq,_>(a,n18,zo,ref out);let(a,x16)=tko::<_,Q2,Sq,_>(a,n18,zo,ref out);let(a,x17)=tko::<_,Q4,Tq,_>(a,n18,zo,ref out);let(a,x18)=tko::<_,20447310,Yj,_>(a,n18,zo,ref out);let(a,x19)=tko::<_,78,67108942,_>(a,n18,zo,ref out);let(a,x20)=tko::<_,0,256,_>(a,n18,zo,ref out);ok=ok&g0(x15,x16,x17,x18,x19,x20);let c=a;let(a,r)=dv::<_,1024,0x3fffffffffffffffffffffffffffff,1023>(x.high,Yl);let x21:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,261888>(r,P8)));out.p(A::qaa(x21,zc));ok=ok&g1(x7,x14,x21);let a=gaa::<_,_,0x138004e00138004e00138004e,0x40000138004e00138004e00138004d>(a,Tg);let(a,x22)=tko::<_,Q0,Uq,_>(a,n18,zo,ref out);let(a,x23)=tko::<_,Q2,Vq,_>(a,n18,zo,ref out);let(a,x24)=tko::<_,Q4,Wq,_>(a,n18,zo,ref out);let(a,x25)=tko::<_,20447310,Xq,_>(a,n18,zo,ref out);let(a,x26)=tko::<_,78,Yq,_>(a,n18,zo,ref out);let(a,x27)=tko::<_,0,1024,_>(a,n18,zo,ref out);ok=ok&g0(x22,x23,x24,x25,x26,x27);let c=match cs::<_,4,3,1024>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Sa;let(a,r)=dv::<_,65536,0xffffffffffffffffffffffffffff,65535>(x.low,Yf);let x28:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,262140>(r,P2)));out.p(A::qaa(x28,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x1000138004e00138004e00138004d>(a,Tg);let(a,x29)=tko::<_,Q0,RE,_>(a,n18,zo,ref out);let(a,x30)=tko::<_,Q2,SE,_>(a,n18,zo,ref out);let(a,x31)=tko::<_,Q4,Xm,_>(a,n18,zo,ref out);let(a,x32)=tko::<_,20447310,TE,_>(a,n18,zo,ref out);let(a,x33)=tko::<_,78,4194382,_>(a,n18,zo,ref out);let(a,x34)=tko::<_,0,16,_>(a,n18,zo,ref out);ok=ok&g0(x29,x30,x31,x32,x33,x34);let c=a;let(a,r)=dv::<_,16384,0x3ffffffffffffffffffffffffffff,16383>(x.high,Vt);let x35:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,262128>(r,P4)));out.p(A::qaa(x35,zc));let a=gaa::<_,_,0x4e00138004e00138004e,0x4000000004e00138004e00138004d>(a,Zq);let(a,x36)=tko::<_,Q2,UE,_>(a,n18,zo,ref out);let(a,x37)=tko::<_,Q4,VE,_>(a,n18,zo,ref out);let(a,x38)=tko::<_,20447310,WE,_>(a,n18,zo,ref out);let(a,x39)=tko::<_,78,XE,_>(a,n18,zo,ref out);let(a,x40)=tko::<_,0,16777216,_>(a,n18,zo,ref out);let c=match cs::<_,65536,65535,16777216>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Ta;let(a,r)=dv::<_,4,0x3fffffffffffffffffffffffffffffff,3>(x.low,N2);let x41:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,196608>(r,Po)));out.p(A::qaa(x41,zc));ok=ok&g1(x28,x35,x41);let a=gaa::<_,_,0x138004e00138004e00138004e,0x4000000138004e00138004e00138004d>(a,Tg);let(a,x42)=tko::<_,Q0,Wt,_>(a,n18,zo,ref out);ok=ok&g0(x36,x37,x38,x39,x40,x42);let(a,x43)=tko::<_,Q2,Xt,_>(a,n18,zo,ref out);let(a,x44)=tko::<_,Q4,Q32,_>(a,n18,zo,ref out);let(a,x45)=tko::<_,20447310,Yt,_>(a,n18,zo,ref out);let(a,x46)=tko::<_,78,Zt,_>(a,n18,zo,ref out);let(a,x47)=tko::<_,0,262144,_>(a,n18,zo,ref out);let y0:Yd=zu(a);out.p(A::qaa(y0,zc));let(a,x48)=tk::<_,0x3fffffffffffffffffffffffffff,_>(x.high,n18,zc,ref out);let a=gaa::<_,_,0x4e00138004e00138004e,0x400000004e00138004e00138004d>(a,Zq);let(a,x49)=tko::<_,Q2,YE,_>(a,n18,zo,ref out);ok=ok&g0(x43,x44,x45,x46,x47,x49);let(a,x50)=tko::<_,Q4,ZE,_>(a,n18,zo,ref out);let(a,x51)=tko::<_,20447310,PF,_>(a,n18,zo,ref out);let(a,x52)=tko::<_,78,QF,_>(a,n18,zo,ref out);let(a,x53)=tko::<_,0,1048576,_>(a,n18,zo,ref out);let c=match cs::<_,4096,4095,1048576>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Ua;let(a,r)=dv::<_,64,0x3ffffffffffffffffffffffffffffff,63>(x.low,N6);let x54:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,258048>(r,Wp)));out.p(A::qaa(x54,zc));ok=ok&g1(y0,x48,x54);let a=gaa::<_,_,0x138004e00138004e00138004e,0x400000138004e00138004e00138004d>(a,Tg);let(a,x55)=tko::<_,Q0,Q8,_>(a,n18,zo,ref out);let(a,x56)=tko::<_,Q2,Q9,_>(a,n18,zo,ref out);ok=ok&g0(x50,x51,x52,x53,x55,x56);let(a,x57)=tko::<_,Q4,Xp,_>(a,n18,zo,ref out);let(a,x58)=tko::<_,20447310,Yp,_>(a,n18,zo,ref out);let(a,x59)=tko::<_,78,Pq,_>(a,n18,zo,ref out);let(a,x60)=tko::<_,0,16384,_>(a,n18,zo,ref out);let c=a;let(a,r)=dv::<_,16,0xfffffffffffffffffffffffffffffff,15>(x.high,N4);let x61:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,245760>(r,Pu)));out.p(A::qaa(x61,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x1000000138004e00138004e00138004d>(a,Tg);let(a,x62)=tko::<_,Q0,Qu,_>(a,n18,zo,ref out);let(a,x63)=tko::<_,Q2,Xl,_>(a,n18,zo,ref out);ok=ok&g0(x57,x58,x59,x60,x62,x63);let(a,x64)=tko::<_,Q4,Ru,_>(a,n18,zo,ref out);let(a,x65)=tko::<_,20447310,Su,_>(a,n18,zo,ref out);let(a,x66)=tko::<_,78,Tu,_>(a,n18,zo,ref out);let(a,x67)=tko::<_,0,65536,_>(a,n18,zo,ref out);let c=match cs::<_,256,255,65536>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Va;let(a,r)=dv::<_,1024,0x3fffffffffffffffffffffffffffff,1023>(x.low,Yl);let x68:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,261888>(r,P8)));out.p(A::qaa(x68,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x40000138004e00138004e00138004d>(a,Tg);let(a,x69)=tko::<_,Q0,Uq,_>(a,n18,zo,ref out);let(a,x70)=tko::<_,Q2,Vq,_>(a,n18,zo,ref out);ok=ok&g0(x64,x65,x66,x67,x69,x70);let(a,x71)=tko::<_,Q4,Wq,_>(a,n18,zo,ref out);let(a,x72)=tko::<_,20447310,Xq,_>(a,n18,zo,ref out);let(a,x73)=tko::<_,78,Yq,_>(a,n18,zo,ref out);let(a,x74)=tko::<_,0,1024,_>(a,n18,zo,ref out);let c=a;let(a,r)=dv::<_,256,0xffffffffffffffffffffffffffffff,255>(x.high,N8);let x75:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,261120>(r,Uu)));out.p(A::qaa(x75,zc));ok=ok&g1(x61,x68,x75);let a=gaa::<_,_,0x138004e00138004e00138004e,0x100000138004e00138004e00138004d>(a,Tg);let(a,x76)=tko::<_,Q0,Q1,_>(a,n18,zo,ref out);let(a,x77)=tko::<_,Q2,Q3,_>(a,n18,zo,ref out);ok=ok&g0(x71,x72,x73,x74,x76,x77);let(a,x78)=tko::<_,Q4,Q5,_>(a,n18,zo,ref out);let(a,x79)=tko::<_,20447310,Q6,_>(a,n18,zo,ref out);let(a,x80)=tko::<_,78,Q7,_>(a,n18,zo,ref out);let(a,x81)=tko::<_,0,4096,_>(a,n18,zo,ref out);let c=match cs::<_,16,15,4096>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Wa;let(a,r)=dv::<_,16384,0x3ffffffffffffffffffffffffffff,16383>(x.low,Vt);let x82:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,262128>(r,P4)));out.p(A::qaa(x82,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x4000138004e00138004e00138004d>(a,Tg);let(a,x83)=tko::<_,Q0,RF,_>(a,n18,zo,ref out);let(a,x84)=tko::<_,Q2,SF,_>(a,n18,zo,ref out);ok=ok&g0(x78,x79,x80,x81,x83,x84);let(a,x85)=tko::<_,Q4,TF,_>(a,n18,zo,ref out);let(a,x86)=tko::<_,20447310,UF,_>(a,n18,zo,ref out);let(a,x87)=tko::<_,78,16777294,_>(a,n18,zo,ref out);let(a,x88)=tko::<_,0,64,_>(a,n18,zo,ref out);let c=a;let(a,r)=dv::<_,4096,0xfffffffffffffffffffffffffffff,4095>(x.high,Qq);let x89:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,262080>(r,P6)));out.p(A::qaa(x89,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x10000138004e00138004e00138004d>(a,Tg);let(a,x90)=tko::<_,Q0,Rq,_>(a,n18,zo,ref out);let(a,x91)=tko::<_,Q2,Sq,_>(a,n18,zo,ref out);ok=ok&g0(x85,x86,x87,x88,x90,x91);let(a,x92)=tko::<_,Q4,Tq,_>(a,n18,zo,ref out);let(a,x93)=tko::<_,20447310,Yj,_>(a,n18,zo,ref out);let(a,x94)=tko::<_,78,67108942,_>(a,n18,zo,ref out);let x95=match constrain::<_,262144,th::F<_,262144,78,262143,67108942>>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};out.p(A::lac(zu(x95),zo));let x95:Yd=zu(x95);let x=Xa;let(a,x96)=tk::<_,0x3fffffffffffffffffffffffffff,_>(x.low,n18,zc,ref out);ok=ok&g1(x82,x89,x96);let a=gaa::<_,_,0x138004e00138004e00138004e,0x400138004e00138004e00138004d>(a,Tg);let(a,x97)=tko::<_,Q0,Ym,_>(a,n18,zo,ref out);let(a,x98)=tko::<_,Q2,VF,_>(a,n18,zo,ref out);ok=ok&g0(x92,x93,x94,x95,x97,x98);let(a,x99)=tko::<_,Q4,WF,_>(a,n18,zo,ref out);let(a,nag)=tko::<_,20447310,XF,_>(a,n18,zo,ref out);let(a,oag)=tko::<_,78,1048654,_>(a,n18,zo,ref out);let(a,pag)=tko::<_,0,4,_>(a,n18,zo,ref out);let c=a;let(a,r)=dv::<_,65536,0xffffffffffffffffffffffffffff,65535>(x.high,Yf);let mad:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,262140>(r,P2)));out.p(A::qaa(mad,zc));let a=gaa::<_,_,0x4e00138004e00138004e,0x1000000004e00138004e00138004d>(a,Zq);let(a,qag)=tko::<_,Q2,YF,_>(a,n18,zo,ref out);let(a,rag)=tko::<_,Q4,PG,_>(a,n18,zo,ref out);ok=ok&g0(x99,nag,oag,pag,qag,rag);let(a,sag)=tko::<_,20447310,QG,_>(a,n18,zo,ref out);let(a,tag)=tko::<_,78,RG,_>(a,n18,zo,ref out);let(a,uag)=tko::<_,0,4194304,_>(a,n18,zo,ref out);let c=match cs::<_,16384,16383,4194304>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Rb;let(a,r)=dv::<_,16,0xfffffffffffffffffffffffffffffff,15>(x.low,N4);let nad:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,245760>(r,Pu)));out.p(A::qaa(nad,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x1000000138004e00138004e00138004d>(a,Tg);let(a,vag)=tko::<_,Q0,Qu,_>(a,n18,zo,ref out);let(a,wag)=tko::<_,Q2,Xl,_>(a,n18,zo,ref out);let(a,xag)=tko::<_,Q4,Ru,_>(a,n18,zo,ref out);ok=ok&g0(sag,tag,uag,vag,wag,xag);let(a,yag)=tko::<_,20447310,Su,_>(a,n18,zo,ref out);let(a,zag)=tko::<_,78,Tu,_>(a,n18,zo,ref out);let(a,aah)=tko::<_,0,65536,_>(a,n18,zo,ref out);let c=a;let(a,r)=dv::<_,4,0x3fffffffffffffffffffffffffffffff,3>(x.high,N2);let oad:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,196608>(r,Po)));out.p(A::qaa(oad,zc));ok=ok&g1(mad,nad,oad);let a=gaa::<_,_,0x138004e00138004e00138004e,0x4000000138004e00138004e00138004d>(a,Tg);let(a,bah)=tko::<_,Q0,Wt,_>(a,n18,zo,ref out);let(a,cah)=tko::<_,Q2,Xt,_>(a,n18,zo,ref out);let(a,dah)=tko::<_,Q4,Q32,_>(a,n18,zo,ref out);ok=ok&g0(yag,zag,aah,bah,cah,dah);let(a,eah)=tko::<_,20447310,Yt,_>(a,n18,zo,ref out);let(a,fah)=tko::<_,78,Zt,_>(a,n18,zo,ref out);let(a,gah)=tko::<_,0,262144,_>(a,n18,zo,ref out);let c=match cs::<_,1024,1023,262144>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=Sb;let(a9,b)=dv::<_,256,0xffffffffffffffffffffffffffffff,255>(x.low,N8);let pad:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,261120>(b,Uu)));out.p(A::qaa(pad,zc));ok=ok&g2(eah,fah,gah,pad);
(ok,a9,x.high)}
#[inline(never)]
fn caj<O,+Drop<O>,impl A:Wi<O>>(ref sig:Span<ZF>,a0:Sm,h0:u128,ok:u128,zc:ZU<131072>,zo:ZU<131150>,ref out:Array<O>)->(u128,ZB<0,0xffffffffff>,u128){let[w1,w2]=(*sig.multi_pop_front::<2>().unwrap()).unbox();let mut ok=ok;let n18=iad();
let a=gaa::<_,_,0x138004e00138004e00138004e,0x100000138004e00138004e00138004d>(a0,Tg);let(a,x1)=tko::<_,Q0,Q1,_>(a,n18,zo,ref out);let(a,x2)=tko::<_,Q2,Q3,_>(a,n18,zo,ref out);let(a,x3)=tko::<_,Q4,Q5,_>(a,n18,zo,ref out);let(a,x4)=tko::<_,20447310,Q6,_>(a,n18,zo,ref out);let(a,x5)=tko::<_,78,Q7,_>(a,n18,zo,ref out);let(a,x6)=tko::<_,0,4096,_>(a,n18,zo,ref out);ok=ok&g0(x1,x2,x3,x4,x5,x6);let c=a;let(a,r)=dv::<_,64,0x3ffffffffffffffffffffffffffffff,63>(h0,N6);let x7:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,258048>(r,Wp)));out.p(A::qaa(x7,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x400000138004e00138004e00138004d>(a,Tg);let(a,x8)=tko::<_,Q0,Q8,_>(a,n18,zo,ref out);let(a,x9)=tko::<_,Q2,Q9,_>(a,n18,zo,ref out);let(a,x10)=tko::<_,Q4,Xp,_>(a,n18,zo,ref out);let(a,x11)=tko::<_,20447310,Yp,_>(a,n18,zo,ref out);let(a,x12)=tko::<_,78,Pq,_>(a,n18,zo,ref out);let(a,x13)=tko::<_,0,16384,_>(a,n18,zo,ref out);ok=ok&g0(x8,x9,x10,x11,x12,x13);let c=match cs::<_,64,63,16384>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x=match us(w1){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return (0,0,0);}};let(a,r)=dv::<_,4096,0xfffffffffffffffffffffffffffff,4095>(x.low,Qq);let x14:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,262080>(r,P6)));out.p(A::qaa(x14,zc));let a=gaa::<_,_,0x138004e00138004e00138004e,0x10000138004e00138004e00138004d>(a,Tg);let(a,x15)=tko::<_,Q0,Rq,_>(a,n18,zo,ref out);let(a,x16)=tko::<_,Q2,Sq,_>(a,n18,zo,ref out);let(a,x17)=tko::<_,Q4,Tq,_>(a,n18,zo,ref out);let(a,x18)=tko::<_,20447310,Yj,_>(a,n18,zo,ref out);let(a,x19)=tko::<_,78,67108942,_>(a,n18,zo,ref out);let(a,x20)=tko::<_,0,256,_>(a,n18,zo,ref out);ok=ok&g0(x15,x16,x17,x18,x19,x20);let c=a;let(a,r)=dv::<_,1024,0x3fffffffffffffffffffffffffffff,1023>(x.high,Yl);let x21:Yd=zu(gaa::<_,_,0,262144>(c,kaa::<_,_,0,261888>(r,P8)));out.p(A::qaa(x21,zc));ok=ok&g1(x7,x14,x21);let a=gaa::<_,_,0x138004e00138004e00138004e,0x40000138004e00138004e00138004d>(a,Tg);let(a,x22)=tko::<_,Q0,Uq,_>(a,n18,zo,ref out);let(a,x23)=tko::<_,Q2,Vq,_>(a,n18,zo,ref out);let(a,x24)=tko::<_,Q4,Wq,_>(a,n18,zo,ref out);let(a,x25)=tko::<_,20447310,Xq,_>(a,n18,zo,ref out);let(a,x26)=tko::<_,78,Yq,_>(a,n18,zo,ref out);let(a,x27)=tko::<_,0,1024,_>(a,n18,zo,ref out);ok=ok&g0(x22,x23,x24,x25,x26,x27);let c=match cs::<_,4,3,1024>(a){Ok(v)=>v,Err(_)=>{return (0,0,0);}};let x:u256=w2.into();let(a,r)=dv::<_,65536,0xffffffffffffffffffffffffffff,65535>(x.low,Yf);let x28:Yd=zu(gaa::<_,_,0,262143>(c,kaa::<_,_,0,262140>(r,P2)));out.p(A::qaa(x28,zc));let(a,x29)=tk::<_,0x3fffffffffffffffffffffff,_>(a,n18,zc,ref out);let(a,x30)=tk::<_,0xfffffffffffffffffff,_>(a,n18,zc,ref out);ok=ok&g1(x28,x29,x30);let(a,x31)=tk::<_,0x3ffffffffffffff,_>(a,n18,zc,ref out);let(a,x32)=tk::<_,0xffffffffff,_>(a,n18,zc,ref out);ok=ok&g3(x31,x32);
(ok,a,x.high)}
const N2:NonZero<ZU<4>>=4;
const N4:NonZero<ZU<16>>=16;
const N6:NonZero<ZU<64>>=64;
const N8:NonZero<ZU<256>>=256;
const Yl:NonZero<ZU<1024>>=1024;
const Qq:NonZero<ZU<4096>>=4096;
const Vt:NonZero<ZU<16384>>=16384;
const Yf:NonZero<ZU<65536>>=65536;

#[inline(always)]
pub fn z_from_felts(sig:Span<ZF>)->Option<Array<ZF>>{match jad(sig){Some((z,_,_,_))=>Some(z),None=>None}}
#[inline(always)]
pub(crate)fn zab(sig:Span<ZF>)->Option<(Array<crate::Z>,ZB<0,255>,ZB<0,0xffffffffff>,u128)>{jad(sig)}
fn jad<O,+Drop<O>,impl A:Wi<O>>(sig:Span<ZF>)->Option<(Array<O>,ZB<0,255>,ZB<0,0xffffffffff>,u128)>{
let zc:ZU<131072>=131072;let zo:ZU<131150>=131150;
let mut out:Array<O>=array![];
let mut ok:u128=0xffffffffffffffffffffffffffffffff;
let mut zs2=sig;let[_,s1]=(*zs2.multi_pop_front::<2>().unwrap()).unbox();let x=match us(s1){R::Wide((h,l))=>u256{low:l,high:h},R::Narrow(_)=>{return None;}};let(a,b1)=dv::<_,256,0xffffffffffffffffffffffffffffff,255>(x.low,N8);let h=x.high;
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,a,h)=gab(ref zs2,a,h,ok,zc,zo,ref out);
let(ok,ta,th)=caj(ref zs2,a,h,ok,zc,zo,ref out);
if ok&Yi !=Yi{
return None;
}
Some((out,b1,ta,th))
}
const P2:ZU<4>=4;
const P4:ZU<16>=16;
const P6:ZU<64>=64;
const P8:ZU<256>=256;
const Uu:ZU<1024>=1024;
const Wp:ZU<4096>=4096;
const Pu:ZU<16384>=16384;
const Po:ZU<65536>=65536;

const Tg:ZU<0x138004e00138004e00138004e>=0x138004e00138004e00138004e;
const Zq:ZU<0x4e00138004e00138004e>=0x4e00138004e00138004e;
const Vu:ZU<524288>=524288;
const Wu:ZU<274877906944>=274877906944;
const SG:ZU<0x200000000000000>=0x200000000000000;
const TG:ZU<0x10000000000000000000>=0x10000000000000000000;
const UG:ZU<0x800000000000000000000000>=0x800000000000000000000000;
const VG:ZU<0x1ffb1bff637fec6ffd8dffb1bff63>=0x1ffb1bff637fec6ffd8dffb1bff63;
const WG:ZU<0x3ffd8bffb1fff62ffec7ffd8bffb1>=0x3ffd8bffb1fff62ffec7ffd8bffb1;
const XG:ZU<0x200007ffb17ff62ffd8dffb1bff63>=0x200007ffb17ff62ffd8dffb1bff63;
const YG:ZU<0x2000040000fff62ffec7ffd8bffb1>=0x2000040000fff62ffec7ffd8bffb1;
#[inline(always)]
fn g0(x0:Yd,x1:Yd,x2:Yd,x3:Yd,x4:Yd,x5:Yd)->u128{zu(gaa::<_,_,0x1ffb1bff637fec6ffd8dffb1bff63,0x3ffb1fff63ffec7ffd8fffb1fff63>(gaa::<_,_,0,0x20000400008000100002000040000>(gaa::<_,_,0,0x400008000100002000040000>(gaa::<_,_,0,0x8000100002000040000>(gaa::<_,_,0,72057731477143552>(gaa::<_,_,0,137439215616>(x0,kaa::<_,_,0,137438953472>(x1,Vu)),kaa::<_,_,0,72057594037927936>(x2,Wu)),kaa::<_,_,0,0x8000000000000000000>(x3,SG)),kaa::<_,_,0,0x400000000000000000000000>(x4,TG)),kaa::<_,_,0,0x20000000000000000000000000000>(x5,UG)),VG))}
#[inline(always)]
const Xu:ZU<-524287>=-524287;
const Yu:ZU<-144114913197948928>=-144114913197948928;
const ZG:ZU<-39614005699268442882448556032>=-39614005699268442882448556032;
fn g1(x0:Yd,x2:Yd,x4:Yd)->u128{
let p0=kaa::<_,_,-137438691328,0>(x0,Xu);
let p1=kaa::<_,_,-37778859805363123781632,0>(x2,Yu);
let p2=kaa::<_,_,-10384573910029026690976594272452608,0>(x4,ZG);
let s01=gaa::<_,_,-37778859805500562472960,0>(p0,p1);
let xah=gaa::<_,_,-10384573910066805550782094834925568,0>(s01,p2);
zu(gaa::<_,_,10381503812800295404404322182627249,20766077722867100955186417017552817>(xah,WG))
}
#[inline(always)]
const PH:ZU<-75557719610726247563264>=-75557719610726247563264;
fn g2(x0:Yd,x1:Yd,x2:Yd,x3:Yd)->u128{
let s01=gaa::<_,_,0,137439215616>(x0,kaa::<_,_,0,137438953472>(x1,Vu));
let xah=gaa::<_,_,0,72057731477143552>(s01,kaa::<_,_,0,72057594037927936>(x2,Wu));
let p3=kaa::<_,_,-19807002849634221441224278016,0>(x3,PH);
let s=gaa::<_,_,-19807002849634221441224278016,72057731477143552>(xah,p3);
zu(gaa::<_,_,0x200003ffb1fff62ffd8dffb1bff63,0x200007ffb17ff63ffd8fffb1fff63>(s,XG))
}
#[inline(always)]
fn g3(x0:Yd,x2:Yd)->u128{
let p0=kaa::<_,_,-137438691328,0>(x0,Xu);
let p1=kaa::<_,_,-37778859805363123781632,0>(x2,Yu);
let s=gaa::<_,_,-37778859805500562472960,0>(p0,p1);
zu(gaa::<_,_,0x20000400007ff63ffec5ffd8fffb1,0x2000040000fff62ffec7ffd8bffb1>(s,YG))
}
const Q0:felt252=0x4e00138004e00138004e;
const Q1:felt252=0x4000004e00138004e00138004e;
const Q2:felt252=0x138004e00138004e;
const Q3:felt252=0x100000138004e00138004e;
const Q4:felt252=5360139632718;
const Q5:felt252=0x4000004e00138004e;
const Q6:felt252=281474997157966;
const Q7:felt252=1073741902;
const Q8:felt252=0x10000004e00138004e00138004e;
const Q9:felt252=0x400000138004e00138004e;
const Xp:felt252=0x10000004e00138004e;
const Yp:felt252=0x400000138004e;
const Pq:felt252=4294967374;
const Rq:felt252=0x400004e00138004e00138004e;
const Sq:felt252=0x10000138004e00138004e;
const Tq:felt252=0x400004e00138004e;
const Yj:felt252=17592206491726;
const Uq:felt252=0x1000004e00138004e00138004e;
const Vq:felt252=0x40000138004e00138004e;
const Wq:felt252=0x1000004e00138004e;
const Xq:felt252=70368764624974;
const Yq:felt252=268435534;
const RE:felt252=0x40004e00138004e00138004e;
const SE:felt252=0x1000138004e00138004e;
const Xm:felt252=0x40004e00138004e;
const TE:felt252=1099532075086;
const UE:felt252=0x100000000138004e00138004e;
const VE:felt252=0x4000000004e00138004e;
const WE:felt252=0x100000000138004e;
const XE:felt252=4398046511182;
const Wt:felt252=0x100000004e00138004e00138004e;
const Xt:felt252=0x4000000138004e00138004e;
const Q32:felt252=0x100000004e00138004e;
const Yt:felt252=0x4000000138004e;
const Zt:felt252=68719476814;
const YE:felt252=0x10000000138004e00138004e;
const ZE:felt252=0x400000004e00138004e;
const PF:felt252=72057594058375246;
const QF:felt252=274877907022;
const Qu:felt252=0x40000004e00138004e00138004e;
const Xl:felt252=0x1000000138004e00138004e;
const Ru:felt252=0x40000004e00138004e;
const Su:felt252=4503599647817806;
const Tu:felt252=17179869262;
const RF:felt252=0x100004e00138004e00138004e;
const SF:felt252=0x4000138004e00138004e;
const TF:felt252=0x100004e00138004e;
const UF:felt252=4398066958414;
const Ym:felt252=0x10004e00138004e00138004e;
const VF:felt252=0x400138004e00138004e;
const WF:felt252=72062954177560654;
const XF:felt252=274898354254;
const YF:felt252=0x40000000138004e00138004e;
const PG:felt252=0x1000000004e00138004e;
const QG:felt252=0x40000000138004e;
const RG:felt252=1099511627854;
const Tm:NonZero<ZU<0x40000>>=0x40000;
// qalias
type ZF=felt252;

/// 2^18 as a cell for every digit division of a period.
#[inline(never)]
fn iad()->NonZero<ZU<0x40000>>{Tm}
