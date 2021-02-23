# frequency variables
start_freq = 1
end_freq = 3
freq_step = 0.5

# power variables
start_power = -30
end_power = -5
power_step = 5

# Get current frequency and power values
for frequency in range(start_freq, end_freq, freq_step):
    for power in range(start_power, end_power, power_step):
        print(f"The frequency is {frequency} and the power is {power}")
        