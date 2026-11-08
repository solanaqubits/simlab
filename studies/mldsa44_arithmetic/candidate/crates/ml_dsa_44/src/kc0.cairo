use crate::k2::Ap;
const MASK64:u128=0xffffffffffffffff;
const ROUND_CONSTANTS:[u128;24]=[
0x0000000000000001,0x0000000000008082,0x800000000000808a,0x8000000080008000,
0x000000000000808b,0x0000000080000001,0x8000000080008081,0x8000000000008009,
0x000000000000008a,0x0000000000000088,0x0000000080008009,0x000000008000000a,
0x000000008000808b,0x800000000000008b,0x8000000000008089,0x8000000000008003,
0x8000000000008002,0x8000000000000080,0x000000000000800a,0x800000008000000a,
0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008,
];
#[inline(always)]
fn rotl(x:u128,pow:ZF,two64:NonZero<u128>)->u128{
let wide:u128=(x.into()*pow).try_into().unwrap();
let(hi,lo)=DivRem::div_rem(wide,two64);
lo+hi
}
#[inline(always)]
pub fn keccak_f1600(state:[u128;25])->[u128;25]{
let mut out:Array<u128>=array![];
for w in crate::k2::keccak_f1600_x2(state).span(){
let(lane,_)=crate::x2::qai(*w);
out.p(lane);
}
let o=out.span();
[*o[0],*o[1],*o[2],*o[3],*o[4],*o[5],*o[6],*o[7],*o[8],*o[9],*o[10],*o[11],*o[12],*o[13],*o[14],*o[15],*o[16],*o[17],*o[18],*o[19],*o[20],*o[21],*o[22],*o[23],*o[24]]
}
pub const SHAKE128_RATE:u32=168;
pub const SHAKE256_RATE:u32=136;
pub fn absorb(input:Span<u8>,rate:u32)->[u128;25]{
let lanes=rate / 8;
let mut state=[0_u128;25];
let mut rest=input;
while rest.len()>=rate{
state=keccak_f1600(xor_block(state,rest.slice(0,rate),lanes));
rest=rest.slice(rate,rest.len()-rate);
}
let mut last:Array<u8>=array![];
last.append_span(rest);
if last.len()==rate-1{
last.p(0x9f);
}else{
last.p(0x1f);
while last.len()!=rate-1{
last.p(0);
}
last.p(0x80);
}
keccak_f1600(xor_block(state,last.span(),lanes))
}
pub fn squeeze(state:[u128;25],lanes:u32)->Array<u8>{
let byte:NonZero<u128>=256_u128.try_into().unwrap();
let mut out:Array<u8>=array![];
let mut lane=0;
for s in state.span(){
if lane==lanes{
break;
}
let mut rest:u128=*s;
let mut k=0;
while k !=8{
let(above,low)=DivRem::div_rem(rest,byte);
out.p(low.try_into().unwrap());
rest=above;
k+=1;
}
lane+=1;
}
out
}
pub fn shake256(input:Span<u8>,out_bytes:u32)->Array<u8>{
let mut state=absorb(input,SHAKE256_RATE);
let mut out:Array<u8>=array![];
loop{
let block=squeeze(state,SHAKE256_RATE / 8);
let take=if out_bytes-out.len()<SHAKE256_RATE{
out_bytes-out.len()
}else{
SHAKE256_RATE
};
out.append_span(block.span().slice(0,take));
if out.len()==out_bytes{
break;
}
state=keccak_f1600(state);
}
out
}
fn xor_block(state:[u128;25],block:Span<u8>,lanes:u32)->[u128;25]{
let[
s0,
s1,
s2,
s3,
s4,
s5,
s6,
s7,
s8,
s9,
s10,
s11,
s12,
s13,
s14,
s15,
s16,
s17,
s18,
s19,
s20,
s21,
s22,
s23,
s24,
]=
state;
let mut b=block;
let s0=s0^lane(ref b);
let s1=s1^lane(ref b);
let s2=s2^lane(ref b);
let s3=s3^lane(ref b);
let s4=s4^lane(ref b);
let s5=s5^lane(ref b);
let s6=s6^lane(ref b);
let s7=s7^lane(ref b);
let s8=s8^lane(ref b);
let s9=s9^lane(ref b);
let s10=s10^lane(ref b);
let s11=s11^lane(ref b);
let s12=s12^lane(ref b);
let s13=s13^lane(ref b);
let s14=s14^lane(ref b);
let s15=s15^lane(ref b);
let s16=s16^lane(ref b);
if lanes==17{
return[
s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15,s16,s17,s18,
s19,s20,s21,s22,s23,s24,
];
}
let s17=s17^lane(ref b);
let s18=s18^lane(ref b);
let s19=s19^lane(ref b);
let s20=s20^lane(ref b);
[
s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15,s16,s17,s18,s19,
s20,s21,s22,s23,s24,
]
}
#[inline(always)]
fn lane(ref bytes:Span<u8>)->u128{
let[b0,b1,b2,b3,b4,b5,b6,b7]=(*bytes.multi_pop_front::<8>().unwrap()).unbox();
let v:ZF=b0.into()
+0x100*b1.into()
+0x10000*b2.into()
+0x1000000*b3.into()
+0x100000000*b4.into()
+0x10000000000*b5.into()
+0x1000000000000*b6.into()
+0x100000000000000*b7.into();
v.try_into().unwrap()
}
pub fn iab(words:Span<u64>)->u256{
let mut out:Array<u64>=array![];
out.append_span(words);
let mut n=words.len();
out.p(0x1f);
n+=1;
while n % 17 !=16{
out.p(0);
n+=1;
}
out.p(0x8000000000000000);
starknet::SyscallResultTrait::unwrap_syscall(starknet::syscalls::keccak_syscall(out.span()))
}
type ZF=felt252;
