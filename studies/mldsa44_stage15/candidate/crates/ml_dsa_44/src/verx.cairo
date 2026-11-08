use crate::k2::Ap;
use crate::kc0::shake256;
use crate::nt0::ntt;
use crate::pk0::{hint_valid,wab,zaa,z_unpack};
use crate::sa0::{fab,expand_a};
pub const PK_BYTES:u32=1312;
pub const SIG_BYTES:u32=2420;
const C_TILDE_BYTES:u32=32;
const T1_BYTES:u32=320;
const Z_BYTES:u32=576;
const HINT_AT:u32=2336;
const OMEGA:u32=80;
use corelib_imports::bounded_int::upcast;
pub fn verify_internal(pk:Span<u8>,message_prime:Span<u8>,sig:Span<u8>)->bool{
if pk.len()!=PK_BYTES{
return false;
}
let tr=shake256(pk,64);
let mut input:Array<u8>=array![];
input.append_span(tr.span());
input.append_span(message_prime);
let mu=shake256(input.span(),64);
verify_mu(pk,mu.span(),sig)
}
pub fn verify_mu(pk:Span<u8>,mu:Span<u8>,sig:Span<u8>)->bool{
cad(pk,mu,sig,Option::None,Option::None)
}
pub fn cad(
pk:Span<u8>,mu:Span<u8>,sig:Span<u8>,zf:Option<Span<ZF>>,
pre:Option<(Span<Span<crate::sa0::Za>>,Span<ZF>)>,
)->bool{
dad(pk,mu,sig,zf,pre,None,None)
}
pub fn dad(
pk:Span<u8>,mu:Span<u8>,sig:Span<u8>,zf:Option<Span<ZF>>,
pre:Option<(Span<Span<crate::sa0::Za>>,Span<ZF>)>,muw:Option<Span<u128>>,ctv:Option<u256>,
)->bool{
let ia=if ctv.is_some(){
OMEGA+4
}else if zf.is_some(){
C_TILDE_BYTES+OMEGA+4
}else{
SIG_BYTES
};
if(pre.is_none()&&pk.len()!=PK_BYTES)||sig.len()!=ia||(muw.is_none()&&mu.len()!=64){
return false;
}
let hint=sig.slice(ia-OMEGA-4,OMEGA+4);
if !hint_valid(hint){
return false;
}
let mut z_hat:Array<Span<crate::nttu::Ya>>=array![];
match zf{
Some(zs)=>{
let mut j=0;
while j !=4{
z_hat.p(ntt(zs.slice(256*j,256)).span());
j+=1;
}
},
None=>{
let mut j=0;
while j !=4{
match z_unpack(sig.slice(C_TILDE_BYTES+Z_BYTES*j,Z_BYTES)){
Some(z)=>z_hat.p(ntt(z.span()).span()),
None=>{break;},
}
j+=1;
}
},
}
if z_hat.len()!=4{
return false;
}
let z_hat=z_hat.span();
let(a_hat,ib)=match pre{
Some((a,t))=>(a,Some(t)),
None=>(expand_a(pk.slice(0,32)).span(),None),
};
let c_tilde=if ctv.is_some(){
sig.slice(0,0)
}else{
sig.slice(0,C_TILDE_BYTES)
};
let pab=match ctv{
Some(v)=>{
let n64:NonZero<u128>=0x10000000000000000_u128.try_into().unwrap();
let(l1,l0)=DivRem::div_rem(v.low,n64);
let(l3,l2)=DivRem::div_rem(v.high,n64);
crate::sa0::xab(l0,l1,l2,l3)
},
None=>fab(c_tilde),
};
let f:Span<ZF>=match ib{
Some(t)=>t,
None=>{
let mut oa:Array<ZF>=array![];
let mut sc:ZF=0x2000;
let mut i=0;
while i !=4{
wab(pk.slice(32+T1_BYTES*i,T1_BYTES),sc,ref oa);
sc*=0x80000000;
i+=1;
}
crate::ct::mai(oa.span()).span()
},
};
let eac=crate::ct::zac(crate::ct::yah(f,pab.span()).span());
let mut h_input:Array<u64>=array![];
if let Some(w)=muw{
for l in w{
h_input.p((*l).try_into().unwrap());
}
}
let mut mb=mu;
while let Some(g)=mb.multi_pop_front::<8>(){
let[b0,b1,b2,b3,b4,b5,b6,b7]=(*g).unbox();
let v:ZF=b0.into()+0x100*b1.into()+0x10000*b2.into()+0x1000000*b3.into()
+0x100000000*b4.into()+0x10000000000*b5.into()+0x1000000000000*b6.into()
+0x100000000000000*b7.into();
h_input.p(v.try_into().unwrap());
}
let mut first:u32=0;
let mut i=0;
while i !=4{
let mut s4=a_hat.slice(4*i,4);let(w_approx,wl)=crate::nttu::mab(ref s4,z_hat,eac.at(i).span());
let end:u32=(*hint.at(OMEGA+i)).into();
zaa(w_approx.span(),hint.slice(first,end-first),ref h_input);
first=end;
i+=1;
}
if let Some(v)=ctv{
return crate::kc0::iab(h_input.span())==v;
}
let mut ct=c_tilde;
let mut low:u128=0;
let mut high:u128=0;
let mut scale:u128=1;
let mut k=0;
while k !=16{
low+=(*ct.pop_front().unwrap()).into()*scale;
if k !=15{
scale*=256;
}
k+=1;
}
scale=1;
k=0;
while k !=16{
high+=(*ct.pop_front().unwrap()).into()*scale;
if k !=15{
scale*=256;
}
k+=1;
}
crate::kc0::iab(h_input.span())==u256{low,high}
}
use corelib_imports::bounded_int::{BoundedInt as B,DivRemHelper as D,MulHelper as M,AddHelper as A,UnitInt as U,bounded_int_div_rem as dr,bounded_int as bi};
#[inline(always)]pub fn bai(mh:ZF)->[u128;5]{
let v:u256=mh.into();
let(p,q)=dr(core::integer::u128_byte_reverse(v.high),N8);let(c,l9)=dr(p,N6);
let(r,s)=dr(core::integer::u128_byte_reverse(v.low),N8);let(t,lb)=dr(r,N6);
let a:Y=bi::mul(q,S6);let b:Y=bi::mul(s,S6);let e:B<0,0xffffffffffffffff> =bi::add(c,b);let f:B<0x1f0000,0x1fffff> =bi::add(t,SP);
[upcast(a),upcast(l9),upcast(e),upcast(lb),upcast(f)]
}
type Q=B<0,0xffffffffffffffffffff>;type X=B<0,0xffffffffffff>;type W=B<0,0xffff>;type Y=B<0,0xffffffffffff0000>;
const N8:NonZero<U<0x1000000000000>> =0x1000000000000;const N6:NonZero<U<0x10000000000000000>> =0x10000000000000000;const S6:U<0x10000> =0x10000;const SP:U<0x1f0000> =0x1f0000;
impl G1 of D<u128,U<0x1000000000000>>{type DivT=Q;type RemT=X;}impl G2 of D<Q,U<0x10000000000000000>>{type DivT=W;type RemT=B<0,0xffffffffffffffff>;}
impl G3 of M<X,U<0x10000>>{type Result=Y;}impl G4 of A<W,Y>{type Result=B<0,0xffffffffffffffff>;}impl G5 of A<W,U<0x1f0000>>{type Result=B<0x1f0000,0x1fffff>;}
pub fn tac(pk:Span<ZF>,sig:Span<ZF>,mh:ZF)->bool{
if sig.len()!=79{
return false;
}
let(z,b31,ha,hh)=match crate::zread::zab(sig){
Some(z)=>z,
None=>{return false;},
};
let f0:u256=(*sig.at(0)).into();
let fh=match core::internal::bounded_int::constrain::<_,0x1000000000000000000000000000000,crate::pk0::th::C<_,0x1000000000000000000000000000000,0xffffffffffffffffffffffffffffff,0xffffffffffffffffffffffffffffffff>>(f0.high){Ok(v)=>v,Err(_)=>{return false;}};
let hb=crate::pk0::kaa::<_,_,0,0xff000000000000000000000000000000>(b31,Uy);
let ctv=u256{low:f0.low,high:upcast(crate::pk0::gaa::<_,_,0,0xffffffffffffffffffffffffffffffff>(fh,hb))};
let tail=match crate::pk0::kac(ha,hh,sig){
Some(b)=>b,
None=>{return false;},
};
let hint=tail.span();
let lanes=match crate::pk0::lah(pk){
Some(l)=>l,
None=>{return false;},
};
let he=match crate::pk0::dac(hint){Some(c)=>c,None=>{return false;}};
let(tr,a0,a1)=crate::x2::xai(lanes.span());
let mut a_hat:Array<Span<crate::sa0::Za>>=array![a0,a1];
let mut ls=lanes.span();let[l0,l1,l2,l3]=(*ls.multi_pop_front::<4>().unwrap()).unbox();
crate::x2::uab(l0,l1,l2,l3,1,ref a_hat);
let(c0,c1)=crate::x2::maa(ctv.low,0x10000000000000000);
let(c2,c3)=crate::x2::maa(ctv.high,0x10000000000000000);
let(muw,pab)=crate::x2::cai(tr.span(),bai(mh),[c0,c1,c2,c3]);
let f=crate::pk0::cac(lanes.span());
ead(hint,he,z.span(),a_hat.span(),f.span(),muw,ctv,pab.span())
}
fn ead(
hint:Span<u8>,he:[u8;4],zs:Span<crate::Z>,a_hat:Span<Span<crate::sa0::Za>>,f:Span<ZF>,
muw:Array<u64>,ctv:u256,pab:Span<u32>,
)->bool{
let mut zw=zs;
let z_hat=array![
crate::nttu::rac(ref zw).span(),crate::nttu::rac(ref zw).span(),
crate::nttu::rac(ref zw).span(),crate::nttu::rac(ref zw).span(),
];
let z_hat=z_hat.span();
let eac=crate::ct::bac(crate::ct::yah(f,pab).span());
let mut h_input:Array<u64>=muw;
let mut first:u32=0;
let[ia,oa,ib,ob]=(eac.span().multi_pop_front::<4>().unwrap()).as_snapshot().unbox();
let[ic,oc,od,ie]=he;
let mut ah=a_hat;
let(w_approx,wl)=crate::nttu::mab(ref ah,z_hat,ia.span());
let end:u32=Into::<u8,u32>::into(ic);
crate::pk0::eab(wl,w_approx.span(),hint.slice(first,end-first),ref h_input);
first=end;
let(w_approx,wl)=crate::nttu::mab(ref ah,z_hat,oa.span());
let end:u32=Into::<u8,u32>::into(oc);
crate::pk0::eab(wl,w_approx.span(),hint.slice(first,end-first),ref h_input);
first=end;
let(w_approx,wl)=crate::nttu::mab(ref ah,z_hat,ib.span());
let end:u32=Into::<u8,u32>::into(od);
crate::pk0::eab(wl,w_approx.span(),hint.slice(first,end-first),ref h_input);
first=end;
let(w_approx,wl)=crate::nttu::mab(ref ah,z_hat,ob.span());
let end:u32=Into::<u8,u32>::into(ie);
crate::pk0::eab(wl,w_approx.span(),hint.slice(first,end-first),ref h_input);
h_input.p(0x1f);
h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0);h_input.p(0x8000000000000000);
starknet::SyscallResultTrait::unwrap_syscall(starknet::syscalls::keccak_syscall(h_input.span()))==ctv
}
type ZF=felt252;
const Uy:corelib_imports::bounded_int::UnitInt<0x1000000000000000000000000000000>=0x1000000000000000000000000000000;
