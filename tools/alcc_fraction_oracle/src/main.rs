//! Bounded second oracle, adapted from the Fable audit fraction_oracle prototype.
//! This is not verified Lean code. Checked i128 arithmetic may refuse valid inputs.
use std::collections::BTreeMap;
use std::io::Read;

#[derive(Clone, Copy, Debug, PartialEq)]
enum Error { Invalid, Range, Limit, Io }
type Result<T> = std::result::Result<T, Error>;

fn gcd(mut a: i128, mut b: i128) -> Result<i128> {
    a = a.checked_abs().ok_or(Error::Range)?;
    b = b.checked_abs().ok_or(Error::Range)?;
    while b != 0 { let r = a % b; a = b; b = r; }
    Ok(a)
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Frac { n: i128, d: i128 }
impl Frac {
    fn new(n: i128, d: i128) -> Result<Self> {
        if d <= 0 { return Err(Error::Invalid); }
        let g = gcd(n, d)?;
        Ok(Self { n: n / g, d: d / g })
    }
    fn add(self, other: Self) -> Result<Self> {
        let g = gcd(self.d, other.d)?;
        let d = self.d.checked_mul(other.d / g).ok_or(Error::Range)?;
        let a = self.n.checked_mul(d / self.d).ok_or(Error::Range)?;
        let b = other.n.checked_mul(d / other.d).ok_or(Error::Range)?;
        Self::new(a.checked_add(b).ok_or(Error::Range)?, d)
    }
}

fn integer(token: &str) -> Result<i128> {
    let digits = token.strip_prefix('-').unwrap_or(token);
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return Err(Error::Invalid);
    }
    token.parse().map_err(|_| Error::Range)
}

fn normalize(text: &str) -> Result<String> {
    if text.len() > 1_048_576 { return Err(Error::Limit); }
    let mut sums = BTreeMap::<[u64; 3], Frac>::new();
    let mut count = 0;
    for line in text.lines() {
        if line.trim().is_empty() { continue; }
        count += 1;
        if count > 4096 { return Err(Error::Limit); }
        let words: Vec<_> = line.split_ascii_whitespace().collect();
        if words.len() != 5 { return Err(Error::Invalid); }
        let mut key = [0; 3];
        for i in 0..3 {
            let x = integer(words[i])?;
            if x < 0 { return Err(Error::Invalid); }
            key[i] = x.try_into().map_err(|_| Error::Range)?;
        }
        let f = Frac::new(integer(words[3])?, integer(words[4])?)?;
        let old = sums.get(&key).copied().unwrap_or(Frac { n: 0, d: 1 });
        sums.insert(key, old.add(f)?);
    }
    let items: Vec<_> = sums.iter().rev().filter(|(_, f)| f.n != 0)
        .map(|(k, f)| format!("[[{},{},{}],\"{}\",\"{}\"]", k[0], k[1], k[2], f.n, f.d))
        .collect();
    Ok(format!("[{}]", items.join(",")))
}

fn execute() -> Result<String> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 1 { return Err(Error::Invalid); }
    let file = std::fs::File::open(&args[0]).map_err(|_| Error::Io)?;
    let mut bytes = Vec::new();
    file.take(1_048_577).read_to_end(&mut bytes).map_err(|_| Error::Io)?;
    if bytes.len() > 1_048_576 { return Err(Error::Limit); }
    normalize(std::str::from_utf8(&bytes).map_err(|_| Error::Invalid)?)
}

fn main() {
    let protocol = "ALCC-FRACTION-ORACLE-1";
    let (code, json) = match execute() {
        Ok(reference) => (0, format!("{{\"protocol\":\"{protocol}\",\"status\":\"OK\",\"reference\":{reference}}}")),
        Err(e) => {
            let (code, status) = match e {
                Error::Invalid => (2, "INVALID_INPUT"), Error::Range => (3, "RANGE_EXCEEDED"),
                Error::Limit => (4, "INPUT_LIMIT"), Error::Io => (5, "IO_ERROR"),
            };
            (code, format!("{{\"protocol\":\"{protocol}\",\"status\":\"{status}\"}}"))
        }
    };
    println!("{json}");
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn min_is_range_refusal() {
        assert_eq!(Frac::new(i128::MIN, 1), Err(Error::Range));
    }
    #[test] fn addition_overflow_is_refusal() {
        assert_eq!(Frac::new(i128::MAX, 1).unwrap().add(Frac::new(1, 1).unwrap()), Err(Error::Range));
    }
    #[test] fn cancellation_and_order() {
        assert_eq!(normalize("0 0 0 1 3\n0 0 0 1 6\n2 0 0 -1 2\n").unwrap(),
                   "[[[2,0,0],\"-1\",\"2\"],[[0,0,0],\"1\",\"2\"]]");
        assert_eq!(normalize("1 2 3 -1 7\n1 2 3 1 7\n").unwrap(), "[]");
    }
    #[test] fn invalid_domains() {
        for text in ["0 0 0 1 0", "-1 0 0 1 2", "0 0 0 1 -2", "garbage"] {
            assert_eq!(normalize(text), Err(Error::Invalid));
        }
    }
}
