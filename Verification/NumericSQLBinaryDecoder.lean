/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLExpectedInstance

/-! NumericSQLBinaryDecoder — exact SQL verification support. -/

namespace NumericSQLBinaryDecoder
open NumericRoundingCertificates

/-- Bounded lower-bound search. Never enumerates a binary64 grid. -/
def search (test : ℕ → Bool) : ℕ → ℕ → ℕ → ℕ
  | 0, lo, _ => lo
  | fuel + 1, lo, hi =>
    if lo = hi then lo else
    let mid := lo + (hi - lo) / 2
    if test mid then search test fuel (mid + 1) hi else search test fuel lo mid

theorem search_correct (test : ℕ → Bool) (last m fuel lo hi : ℕ)
    (ht : ∀ j < last, test j = true ↔ j < m)
    (hl : lo ≤ m) (hm : m ≤ hi) (hh : hi ≤ last) (hb : hi - lo < 2 ^ fuel) :
    search test fuel lo hi = m := by
  induction fuel generalizing lo hi with
  | zero => simp only [pow_zero] at hb; simp [search]; omega
  | succ fuel ih =>
    unfold search
    split
    next he => omega
    next he =>
      let mid := lo + (hi - lo) / 2
      have hmid : mid < hi := by dsimp [mid]; omega
      have hml : lo ≤ mid := by dsimp [mid]; omega
      have hp : 2 ^ (fuel + 1) = 2 ^ fuel * 2 := pow_succ _ _
      dsimp only
      split
      next hc =>
        have hm' : mid < m := (ht mid (by omega)).mp hc
        apply ih (mid + 1) hi (by omega) hm hh
        dsimp [mid] at *
        rw [hp] at hb
        omega
      next hc =>
        have hm' : m ≤ mid := by
          by_contra hn
          exact hc ((ht mid (by omega)).mpr (by omega))
        apply ih lo mid hl hm' (by omega)
        dsimp [mid] at *
        rw [hp] at hb
        omega

def code (q : ℚ) : ℕ := search (fun j => decide (crossed binary64 q j)) 64 0 binary64.last

theorem code_correct (q : ℚ) : code q = magnitudeCode binary64 q := by
  apply search_correct
  · intro j hj
    simpa using crossed_iff_lt_code binary64 q j hj
  · omega
  · exact magnitudeCode_le _ _
  · rfl
  · decide +kernel

/-- Zero and infinity are not allowed SQL input parameters. -/
def represented (q : ℚ) : Option ℚ :=
  let k := code q
  if 0 < q ∧ 0 < k ∧ k < binary64.last ∧ inMagnitudeCell binary64 q k
    then some (binary64.value k) else none

/-- Declarative nearest-even cell specification, independent of search. -/
def Represents (q v : ℚ) : Prop :=
  0 < q ∧ ∃ k, 0 < k ∧ k < binary64.last ∧
    inMagnitudeCell binary64 q k ∧ v = binary64.value k

theorem represented_sound (q v : ℚ) (h : represented q = some v) : Represents q v := by
  unfold represented at h
  dsimp only at h
  split at h
  next hs =>
    exact ⟨hs.1, code q, hs.2.1, hs.2.2.1, hs.2.2.2, (Option.some.inj h).symm⟩
  next => contradiction

theorem represented_complete (q v : ℚ) (h : Represents q v) : represented q = some v := by
  obtain ⟨hq, k, hk, hl, hc, hv⟩ := h
  have he : code q = k := (code_correct q).trans (magnitudeCode_of_cell _ _ _ hc)
  simp [represented, he, hq, hk, hl, hc, hv]

theorem represents_unique (q x y : ℚ) (hx : Represents q x) (hy : Represents q y) : x = y := by
  exact Option.some.inj ((represented_complete q x hx).symm.trans (represented_complete q y hy))

theorem represented_rounding (q v : ℚ) (h : represented q = some v) :
    (roundNearestEven binary64 q).decode = FloatValue.finite v := by
  obtain ⟨hq, k, hk, hl, hc, hv⟩ := represented_sound q v h
  have he := magnitudeCode_of_cell binary64 q k hc
  have hz : k ≠ 0 := by omega
  have hi : k ≠ binary64.last := by omega
  simp [roundNearestEven, abs_of_pos hq, he, FloatRepresentation.decode, hz, hi,
    not_lt_of_ge (le_of_lt hq), hv]

end NumericSQLBinaryDecoder
