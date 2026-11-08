pub mod ct;
pub mod encx;
pub use encx as encoding;
mod nttu;
pub mod k2;
pub mod kc0;
pub use kc0 as keccak;
pub mod nt0;
pub use nt0 as ntt;
pub mod pk0;
pub use pk0 as packing;
pub mod sa0;
pub use sa0 as sampling;
pub mod verx;
pub use verx as verify;
pub mod x2;
pub mod zread;
use pqbench_interface::PqSignatureVerifier;
pub const PK_FELTS:u32=43;
pub const SIG_FELTS:u32=79;
pub impl MlDsa44Verifier of PqSignatureVerifier{
fn verify(message_hash:felt252,public_key:Span<felt252>,signature:Span<felt252>)->bool{
verx::tac(public_key,signature,message_hash)
}
}

/// Correction digit wrapper (one field; keeps type names short in the class).
#[derive(Copy,Drop)]
pub struct W{pub v:ct::Rh}
/// z coefficient wrapper (one field; keeps type names short in the class).
#[derive(Copy,Drop)]
pub struct Z{pub v:nttu::Zb}
