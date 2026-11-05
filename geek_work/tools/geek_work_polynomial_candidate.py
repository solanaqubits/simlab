"""Small deterministic interpolation generator; receives training samples only."""
from fractions import Fraction


def multiply(a, b):
    result = [Fraction(0)]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):result[i+j] += x*y
    return result


def candidates(samples):
    # Lagrange interpolation. No checker imports, holdout input, code eval or I/O.
    if len(samples) != 4 or [r['n'] for r in samples] != [0,1,2,3]:
        raise ValueError('fixed four-point training profile required')
    fitted = [Fraction(0)]*4
    for row in samples:
        basis = [Fraction(1)];denominator = 1
        for other in samples:
            if other['n'] != row['n']:
                basis = multiply(basis, [-other['n'],1]);denominator *= row['n']-other['n']
        scale = Fraction(row['sum_squares'], denominator)
        for i,value in enumerate(basis):fitted[i] += value*scale
    injected = fitted[:];injected[1] = -injected[1]
    vanishing = [Fraction(1)]
    for row in samples:vanishing = multiply(vanishing, [-row['n'],1])
    overfit = fitted+[Fraction(0)]
    for i,value in enumerate(vanishing):overfit[i] += value
    def row(name,coefficients):return dict(id=name,coefficients=[str(c) for c in coefficients])
    return [row('null',[Fraction(0)]),row('sign-error',injected),row('training-only',overfit),row('interpolated',fitted)]
