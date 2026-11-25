import pandas as pd
import numpy as np

d = pd.read_csv('data/processed_data.csv')

print('=== PWM distribution ===')
print('Left PWM:')
print(d['pwm_left'].describe())
print('\nRight PWM:')
print(d['pwm_right'].describe())

print('\n=== Thrust distribution ===')
print('tau_X:')
print(d['tau_X'].describe())
print('tau_N:')
print(d['tau_N'].describe())

print('\n=== Speed vs Thrust correlation ===')
active = d[d['tau_X'].abs() > 1]
corr = active['u'].corr(active['tau_X'])
print(f'Correlation u vs tau_X: {corr:.4f}')

# Check if there are periods of clear acceleration/deceleration
print('\n=== Acceleration magnitude ===')
print(d[['u_dot','v_dot','r_dot']].abs().describe())

# Check for stationary periods
static = d[d['gps_speed'] < 0.1]
print(f'\nStationary (speed<0.1): {len(static)}/{len(d)} ({100*len(static)/len(d):.1f}%)')
