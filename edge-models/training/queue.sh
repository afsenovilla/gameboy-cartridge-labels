set -x
P="../venv/bin/python -u train.py --kind heatmap --batch 256 --steps 3000"
for p in 0 1; do
  $P --parts $p --R 10 --tag base
  $P --parts $p --R 10 --jitter 0.1 --tag train-scale-jitter
  $P --parts $p --R 10 --cond 0 --tag no-side-input
  $P --parts $p --R 5 --dil 1 2 4 8 1 --tag R5
  $P --parts $p --R 20 --dil 1 2 4 8 16 32 1 --tag R20
  $P --parts $p --R 10 --dil 1 2 4 1 --tag rf3mm
  $P --parts $p --R 10 --dil 1 2 4 8 1 --tag rf6mm
  $P --parts $p --R 10 --dil 1 2 4 8 16 32 1 --tag rf26mm
done
for sh in cgb agb; do for p in 0 1; do $P --shell $sh --parts $p --R 10 --jitter 0.1 --tag train-scale-jitter; done; done
