import Verification.AlgebraicCertificateVerify
import Lean.Data.Json.Basic

/-! Measurement adapter only: no new theorem or per-input kernel proof. -/
@[noinline] def timedCheck (bp bc : ByteArray) : IO UInt32 := do
  let code := match AlgebraicCertificateVerify.verifyCertificateBytes bp.toList bc.toList with
    | none => 3
    | some true => 0
    | some false => 2
  return code

def main (args : List String) : IO UInt32 := do
  match args with
  | [passport, certificate] =>
    let t0 ← IO.monoNanosNow
    let bp ← IO.FS.readBinFile passport
    let bc ← IO.FS.readBinFile certificate
    let t1 ← IO.monoNanosNow
    let code ← timedCheck bp bc
    let t2 ← IO.monoNanosNow
    IO.println (Lean.Json.mkObj [
      ("schema", Lean.toJson "alcc-native-timing-1"),
      ("evidence_kind", Lean.toJson "compiled_execution"),
      ("code", Lean.toJson code.toNat),
      ("read_ns", Lean.toJson (t1-t0)),
      ("verify_ns", Lean.toJson (t2-t1))]).compress
    return code
  | _ =>
    IO.eprintln "usage: alcc-timed PASSPORT CERTIFICATE"
    return 64
