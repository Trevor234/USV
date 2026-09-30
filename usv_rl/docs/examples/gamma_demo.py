for gamma in [0.9, 0.99, 0.999]:
    w10 = gamma ** 10
    w100 = gamma ** 100
    cap = 1 / (1 - gamma)
    print(f"γ={gamma:<6} 10步后权重={w10:.3f}  100步后权重={w100:.3f}  回报上限={cap:.0f}")
