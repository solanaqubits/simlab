/-
Copyright (c) 2026 aicyberg. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: aicyberg
-/
import Verification.NumericSQLExpectedInstance
import Mathlib.Data.List.TakeWhile

/-! Exact decimal syntax after the external JSON parser. No byte-parser theorem. -/
namespace NumericSQLDecimalDecoder

def digit (c : Char) : Bool := '0' ≤ c && c ≤ '9'
def digitValue (c : Char) : ℕ := c.toNat - '0'.toNat

def positional : List Char → ℕ
  | [] => 0
  | c :: cs => digitValue c * 10 ^ cs.length + positional cs

def accumulate (a : ℕ) (cs : List Char) : ℕ :=
  match cs with
  | [] => a
  | c :: tail => accumulate (a * 10 + digitValue c) tail
termination_by structural cs

theorem accumulate_correct (cs : List Char) (a : ℕ) :
    accumulate a cs = a * 10 ^ cs.length + positional cs := by
  induction cs generalizing a with
  | nil => change a = a * 10 ^ 0 + 0; omega
  | cons c cs ih =>
    change accumulate (a * 10 + digitValue c) cs = _
    rw [ih]
    simp only [List.length_cons, positional, pow_succ]
    ring

structure Lexeme where
  sign : List Char
  whole : List Char
  dot : Bool
  fraction : List Char
  marker : List Char
  exponentSign : List Char
  exponentDigits : List Char
  deriving DecidableEq, Repr

def Lexeme.render (l : Lexeme) : List Char :=
  l.sign ++ l.whole ++ (if l.dot then ['.'] ++ l.fraction else []) ++
    l.marker ++ l.exponentSign ++ l.exponentDigits

def signOK (s : List Char) : Prop := s = [] ∨ s = ['+'] ∨ s = ['-']
instance (s : List Char) : Decidable (signOK s) := inferInstanceAs (Decidable (_ ∨ _ ∨ _))

def Lexeme.Valid (l : Lexeme) : Prop :=
  signOK l.sign ∧ l.whole.all digit = true ∧ l.fraction.all digit = true ∧
  (l.whole ≠ [] ∨ l.dot = true ∧ l.fraction ≠ []) ∧
  (l.dot = false → l.fraction = []) ∧
  ((l.marker = [] ∧ l.exponentSign = [] ∧ l.exponentDigits = []) ∨
   ((l.marker = ['e'] ∨ l.marker = ['E']) ∧ signOK l.exponentSign ∧
      l.exponentDigits ≠ [] ∧ l.exponentDigits.all digit = true))
instance (l : Lexeme) : Decidable l.Valid := inferInstanceAs (Decidable (_ ∧ _ ∧ _ ∧ _ ∧ _ ∧ _))

def signed (sg : List Char) (n : ℕ) : ℤ := if sg = ['-'] then -(n : ℤ) else n

def Lexeme.exponent (l : Lexeme) : ℤ :=
  signed l.exponentSign (accumulate 0 l.exponentDigits) - (l.fraction.length : ℤ)

def decimalScale (n : ℤ) (e : ℤ) : ℚ :=
  if 0 ≤ e then (n : ℚ) * 10 ^ e.toNat else (n : ℚ) / 10 ^ e.natAbs

def Lexeme.value (l : Lexeme) : ℚ :=
  decimalScale (signed l.sign (accumulate 0 (l.whole ++ l.fraction))) l.exponent

/-- Independent positional denotation, not a call to the parser. -/
def Lexeme.denotation (l : Lexeme) : ℚ :=
  decimalScale (signed l.sign (positional (l.whole ++ l.fraction)))
    (signed l.exponentSign (positional l.exponentDigits) - (l.fraction.length : ℤ))

theorem value_eq_denotation (l : Lexeme) : l.value = l.denotation := by
  simp [Lexeme.value, Lexeme.denotation, Lexeme.exponent, accumulate_correct]

def stripSign : List Char → List Char × List Char
  | '+' :: cs => (['+'], cs)
  | '-' :: cs => (['-'], cs)
  | cs => ([], cs)

def lex (cs : List Char) : Lexeme := Id.run do
  let (sg, tail) := stripSign cs
  let whole := tail.takeWhile digit
  let rest := tail.dropWhile digit
  let (dot, frac, rest) := match rest with
    | '.' :: xs => (true, xs.takeWhile digit, xs.dropWhile digit)
    | xs => (false, [], xs)
  let (marker, es, ed) := match rest with
    | 'e' :: xs => let (sg, xs) := stripSign xs; (['e'], sg, xs)
    | 'E' :: xs => let (sg, xs) := stripSign xs; (['E'], sg, xs)
    | _ => ([], [], [])
  return ⟨sg, whole, dot, frac, marker, es, ed⟩

def withinLimits (l : Lexeme) : Prop :=
  l.render.length ≤ 4096 ∧ l.exponentDigits.length ≤ 4 ∧ l.exponent.natAbs ≤ 4096
instance (l : Lexeme) : Decidable (withinLimits l) := inferInstanceAs (Decidable (_ ∧ _ ∧ _))

def decode (cs : List Char) : Option ℚ :=
  let l := lex cs
  if l.Valid ∧ l.render = cs ∧ withinLimits l then some l.value else none

/-- Grammar, positional value and explicit limits; independent of lex/decode. -/
def Represents (cs : List Char) (q : ℚ) : Prop :=
  ∃ l : Lexeme, l.Valid ∧ l.render = cs ∧ withinLimits l ∧ l.denotation = q

theorem decode_sound (cs : List Char) (q : ℚ) (h : decode cs = some q) :
    Represents cs q := by
  unfold decode at h
  dsimp only at h
  split at h
  next hl =>
    obtain ⟨hv, hr, hb⟩ := hl
    exact ⟨lex cs, hv, hr, hb, (value_eq_denotation _).symm.trans (Option.some.inj h)⟩
  next => contradiction

/-- Successful outputs are unique, even for noncanonical source spellings. -/
theorem decode_unique (cs : List Char) (x y : ℚ)
    (hx : decode cs = some x) (hy : decode cs = some y) : x = y := by
  exact Option.some.inj (hx.symm.trans hy)

/-- Normalization means exact positional denotation, never byte equality. -/
def Equivalent (a b : Lexeme) : Prop := a.denotation = b.denotation

theorem normalize_preserves (a b : Lexeme) (h : Equivalent a b) : a.value = b.value := by
  simpa [Equivalent, value_eq_denotation] using h

def integerLexeme (cs : List Char) : Lexeme := ⟨[], cs, false, [], [], [], []⟩

theorem stripSign_digits (cs : List Char) (h : cs.all digit = true) :
    stripSign cs = ([], cs) := by
  cases cs with
  | nil => rfl
  | cons c cs =>
    have hc : digit c = true := (List.all_eq_true.mp h) c (by simp)
    have hp : c ≠ '+' := by intro he; subst c; contradiction
    have hm : c ≠ '-' := by intro he; subst c; contradiction
    simp only [stripSign]
    split <;> simp_all

theorem lex_integer (cs : List Char) (h : cs.all digit = true) :
    lex cs = integerLexeme cs := by
  have ht := List.takeWhile_eq_self_iff.mpr (List.all_eq_true.mp h)
  have hd := List.dropWhile_eq_nil_iff.mpr (List.all_eq_true.mp h)
  simp [lex, stripSign_digits cs h, ht, hd, integerLexeme]

/-- Completeness for unsigned nonempty digit strings, with exact explicit limits.
This is an infinite mathematical family before the profile length bound; it does
not claim completeness for every decimal spelling. -/
theorem decode_integer_complete (cs : List Char) (h : cs.all digit = true)
    (hne : cs ≠ []) (hlen : cs.length ≤ 4096) :
    decode cs = some (positional cs : ℚ) := by
  have hv : (integerLexeme cs).Valid := by
    simp [Lexeme.Valid, integerLexeme, signOK, h, hne]
  have hb : withinLimits (integerLexeme cs) := by
    simp [withinLimits, integerLexeme, Lexeme.render, Lexeme.exponent, signed,
      accumulate_correct, positional, hlen]
  unfold decode
  rw [lex_integer cs h]
  have hr : (integerLexeme cs).render = cs := by simp [integerLexeme, Lexeme.render]
  rw [if_pos ⟨hv, hr, hb⟩]
  congr 1
  simp [integerLexeme, Lexeme.value, Lexeme.exponent, signed, decimalScale,
    accumulate_correct, positional]

end NumericSQLDecimalDecoder
