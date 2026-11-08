use crate::k2::Ap;
const FELT_BYTES:u32=31;
pub fn felts_to_bytes(felts:Span<ZF>,total:u32)->Option<Array<u8>>{
if felts.len()!=(total+FELT_BYTES-1)/ FELT_BYTES{
return None;
}
let mut out:Array<u8>=array![];
let mut remaining=total;
let mut canonical=true;
for felt in felts{
let size=if remaining<FELT_BYTES{
remaining
}else{
FELT_BYTES
};
let value:u256=(*felt).into();
let low_size=if size<16{
size
}else{
16
};
let ia=if low_size==16{
oai(value.low,ref out);
0
}else{
take_le(value.low,low_size,ref out)
};
let oa=if size-low_size==15{
pai(value.high,ref out)
}else{
take_le(value.high,size-low_size,ref out)
};
if ia !=0||oa !=0{
canonical=false;
break;
}
remaining-=size;
}
if canonical{
Some(out)
}else{
None
}
}
fn take_le(x:u128,count:u32,ref out:Array<u8>)->u128{
let byte:NonZero<u128>=256_u128.try_into().unwrap();
let mut rest=x;
let mut k=0;
while k !=count{
let(above,low)=DivRem::div_rem(rest,byte);
out.p(low.try_into().unwrap());
rest=above;
k+=1;
}
rest
}
pub fn message_prime(message_hash:ZF)->Array<u8>{
let value:u256=message_hash.into();
let mut le:Array<u8>=array![];
take_le(value.low,16,ref le);
take_le(value.high,16,ref le);
let mut out:Array<u8>=array![0,0];
let mut bytes=le.span();
while let Some(byte)=bytes.pop_back(){
out.p(*byte);
}
out
}
use corelib_imports::bounded_int::{BoundedInt as ZB,DivRemHelper as ZD,UnitInt as ZU,bounded_int as zq,upcast as zu};
type B8=ZB<0,0xff>;
const Zd:NonZero<ZU<0x100>>=0x100;
impl E0 of ZD<u128,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffffffffffffff>;type RemT=B8;}
impl E1 of ZD<ZB<0,0xffffffffffffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffffffffffff>;type RemT=B8;}
impl E2 of ZD<ZB<0,0xffffffffffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffffffffff>;type RemT=B8;}
impl E3 of ZD<ZB<0,0xffffffffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffffffff>;type RemT=B8;}
impl E4 of ZD<ZB<0,0xffffffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffffff>;type RemT=B8;}
impl E5 of ZD<ZB<0,0xffffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffffff>;type RemT=B8;}
impl E6 of ZD<ZB<0,0xffffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffffff>;type RemT=B8;}
impl E7 of ZD<ZB<0,0xffffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffffff>;type RemT=B8;}
impl E8 of ZD<ZB<0,0xffffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffffff>;type RemT=B8;}
impl E9 of ZD<ZB<0,0xffffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffffff>;type RemT=B8;}
impl E10 of ZD<ZB<0,0xffffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffffff>;type RemT=B8;}
impl E11 of ZD<ZB<0,0xffffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffffff>;type RemT=B8;}
impl E12 of ZD<ZB<0,0xffffffff>,ZU<0x100>>{type DivT=ZB<0,0xffffff>;type RemT=B8;}
impl E13 of ZD<ZB<0,0xffffff>,ZU<0x100>>{type DivT=ZB<0,0xffff>;type RemT=B8;}
impl E14 of ZD<ZB<0,0xffff>,ZU<0x100>>{type DivT=B8;type RemT=B8;}
#[inline(always)]
fn oai(x:u128,ref out:Array<u8>){
let(x,b0)=zq::div_rem(x,Zd);
let(x,b1)=zq::div_rem(x,Zd);
let(x,b2)=zq::div_rem(x,Zd);
let(x,b3)=zq::div_rem(x,Zd);
let(x,b4)=zq::div_rem(x,Zd);
let(x,b5)=zq::div_rem(x,Zd);
let(x,b6)=zq::div_rem(x,Zd);
let(x,b7)=zq::div_rem(x,Zd);
let(x,b8)=zq::div_rem(x,Zd);
let(x,b9)=zq::div_rem(x,Zd);
let(x,b10)=zq::div_rem(x,Zd);
let(x,b11)=zq::div_rem(x,Zd);
let(x,b12)=zq::div_rem(x,Zd);
let(x,b13)=zq::div_rem(x,Zd);
let(b15,b14)=zq::div_rem(x,Zd);
out.append_span([zu(b0),zu(b1),zu(b2),zu(b3),zu(b4),zu(b5),zu(b6),zu(b7),zu(b8),zu(b9),zu(b10),zu(b11),zu(b12),zu(b13),zu(b14),zu(b15)].span());
}
#[inline(always)]
fn pai(x:u128,ref out:Array<u8>)->u128{
let(x,b0)=zq::div_rem(x,Zd);
let(x,b1)=zq::div_rem(x,Zd);
let(x,b2)=zq::div_rem(x,Zd);
let(x,b3)=zq::div_rem(x,Zd);
let(x,b4)=zq::div_rem(x,Zd);
let(x,b5)=zq::div_rem(x,Zd);
let(x,b6)=zq::div_rem(x,Zd);
let(x,b7)=zq::div_rem(x,Zd);
let(x,b8)=zq::div_rem(x,Zd);
let(x,b9)=zq::div_rem(x,Zd);
let(x,b10)=zq::div_rem(x,Zd);
let(x,b11)=zq::div_rem(x,Zd);
let(x,b12)=zq::div_rem(x,Zd);
let(x,b13)=zq::div_rem(x,Zd);
let(rest,b14)=zq::div_rem(x,Zd);
out.append_span([zu(b0),zu(b1),zu(b2),zu(b3),zu(b4),zu(b5),zu(b6),zu(b7),zu(b8),zu(b9),zu(b10),zu(b11),zu(b12),zu(b13),zu(b14)].span());
zu(rest)
}
// qalias
type ZF=felt252;
