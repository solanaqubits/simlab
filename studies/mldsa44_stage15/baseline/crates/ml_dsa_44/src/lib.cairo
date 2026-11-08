//! ML-DSA-44 (NIST FIPS 204) signature verification for Starknet.
//!
//! `MlDsa44Verifier::verify` is ML-DSA.Verify (FIPS 204, Algorithm 3: the pure variant, with the
//! empty context) over this felt encoding:
//!
//! - the message is the transaction hash, a felt, signed as its 32 big-endian bytes, so
//!   M' = 0x00 || 0x00 || M;
//! - the public key (1,312 bytes) and the signature (2,420 bytes) are packed 31 bytes per felt,
//!   little-endian within each felt, the last felt holding the remainder: 43 and 79 felts. A felt
//!   with any bit set above its bytes is malformed, so every key and signature has one encoding.
//!
//! Written from FIPS 204 algorithm by algorithm (numbers in the comments) and checked against
//! NIST's ACVP vectors and an independent Python reference (tests/).

pub mod encoding;
pub mod keccak;
pub mod ntt;
pub mod packing;
pub mod sampling;
pub mod verify;
use pqbench_interface::PqSignatureVerifier;

pub const PK_FELTS: u32 = 43;
pub const SIG_FELTS: u32 = 79;

pub impl MlDsa44Verifier of PqSignatureVerifier {
    fn verify(message_hash: felt252, public_key: Span<felt252>, signature: Span<felt252>) -> bool {
        let pk = match encoding::felts_to_bytes(public_key, verify::PK_BYTES) {
            Some(bytes) => bytes,
            None => { return false; },
        };
        let sig = match encoding::felts_to_bytes(signature, verify::SIG_BYTES) {
            Some(bytes) => bytes,
            None => { return false; },
        };
        verify::verify_internal(pk.span(), encoding::message_prime(message_hash).span(), sig.span())
    }
}
