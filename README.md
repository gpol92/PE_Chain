# PE_Chain
This repository contains an educational SystemVerilog digital circuit to make research on the HW development for AI

Example of usage (--warning let's you to suppress the info messages given by cocotb and Icarus Verilog)\
```python test_pe.py --warning```

Example of output
> [OK] Dot product value equal to expected (2)

Negative value test

```python test_pe.py --no-positive --warning```

Output
> [OK] Dot product value equal to expected (-2)

Zero value test

```python test_pe.py --zero --warning```

Output
> [OK] Dot product value equal to expected (0)
