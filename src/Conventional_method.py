#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import numpy as np
import math

def pick_size_index_for_80pct(peak, sizes, threshold=0.8):
    req = peak / threshold
    for idx, S in enumerate(sizes):
        if S >= req:
            return idx
    return len(sizes) - 1

def conventional_schedule(Peak_Load, Transformer_sizes, n, threshold=0.8):
    I = len(Transformer_sizes)
    x_conv = np.zeros((I, n), dtype=int)
    y_conv = np.zeros((I, n), dtype=int)
    z_conv = np.zeros((I, n), dtype=int)

    year = 0
    while year < n:
        i = pick_size_index_for_80pct(Peak_Load[year], Transformer_sizes, threshold)
        y_conv[i, year] = 1

        # --- Age-based end (existing logic) ---
        life_years = transformer_life(i, year, n + 2)
        life_years = int(max(1, math.ceil(life_years)))
        age_end = min(n, year + life_years)

        # --- Overload-based end  ---
        overload_year = None
        for t in range(year + 1, age_end):
            if Peak_Load[t] > 1.5 * Transformer_sizes[i]:
                overload_year = t
                break

        # --- Whichever comes first wins ---
        if overload_year is not None:
            actual_end = overload_year          # overload hits before age limit
            replaced_early = True
        else:
            actual_end = age_end                # natural end of life
            replaced_early = False

        # Mark active window and removal year
        x_conv[i, year:actual_end] = 1
        if actual_end < n:
            z_conv[i, actual_end] = 1           # removed at actual_end

        year = actual_end
    return x_conv, y_conv, z_conv


# In[ ]:


x_conv, y_conv, z_conv = conventional_schedule(Peak_Load, Transformer_sizes, n, threshold=0.8)


# In[ ]:


def cond_failure_prob_conv(tau_end, ell, eta, beta):
    """Same conditional failure-probability formula used to build p[i,j]
    in the optimizer (see CONSTRAINT 7)."""
    tau_start = max(tau_end - ell, 0.0)
    exponent = (tau_end / eta) ** beta - (tau_start / eta) ** beta
    if exponent >= 100:
        return 1.0
    return min(max(1.0 - np.exp(-exponent), 0.0), 1.0)


def find_install_year(y_conv, i, j):
    """Walk back from year j to find the installation year (y_conv==1) of
    the transformer segment of size i that covers year j."""
    k = j
    while k >= 0 and y_conv[i, k] != 1:
        k -= 1
    return max(k, 0)


def compute_conventional_cost(x_conv, y_conv, z_conv, Peak_Load, Transformer_sizes, n,
                               C_invest, C_replace, Emergenecy_replace_cost,
                               C_electricity, k_core, k_copper, r,
                               Interruption_cost_rate, Interruption_time,
                               sum_sq_by_year, yearly_loss, residual_frac, residual_end,
                               eta, beta):

    I = len(Transformer_sizes)

    # ---------- 1) Investment cost ----------
    Investment_cost_conv = sum(
        y_conv[i, j] * C_invest[i] * (1 / (1 + r) ** j)
        for i in range(I) for j in range(n)
    )

    # ---------- 2) Replacement cost ----------
    Cost_of_transformer_replace_conv = sum(
        z_conv[i, j] * C_replace[i] * (1 / (1 + r) ** j)
        for i in range(I) for j in range(n)
    )

    # ---------- 3) No-load (core) + load (copper) loss cost ----------
    Cost_of_transformer_losses_conv = sum(
        x_conv[i, j] * (
            k_core * Transformer_sizes[i] * 8760 * C_electricity +
            k_copper * (sum_sq_by_year[j] / Transformer_sizes[i]) * C_electricity
        ) * (1 / (1 + r) ** j)
        for i in range(I) for j in range(n)
    )

    # ---------- 4) Age tracking -> conditional failure/outage probability ----------
    p_conv = np.zeros((I, n))
    age = 0.0
    for j in range(n):
        for i in range(I):
            if x_conv[i, j] == 1:
                if y_conv[i, j] == 1:
                    age = 0.0                      # brand-new transformer -> age resets
                ell = yearly_loss[i, j]
                tau_end = age + ell
                p_conv[i, j] = cond_failure_prob_conv(tau_end, ell, eta, beta)
                age = tau_end

    Cost_of_transformer_Outage_conv = sum(
        p_conv[i, j] * x_conv[i, j] * (
            Peak_Load[j] * Interruption_time[i] * C_electricity +
            Peak_Load[j] * Interruption_cost_rate +
            Emergenecy_replace_cost[i]
        ) * (1 / (1 + r) ** j)
        for i in range(I) for j in range(n)
    )

    # ---------- 5) Salvage value ----------
    Salvage_amount_conv = 0.0

    # a) transformers removed/replaced before the end of the horizon
    for i in range(I):
        for j in range(n):
            if z_conv[i, j] == 1:
                k = find_install_year(y_conv, i, j - 1)
                Salvage_amount_conv += C_invest[i] * residual_frac[i][k][j] * (1 / (1 + r) ** j)

    # b) transformer still in service at the very end of the planning horizon
    for i in range(I):
        if x_conv[i, n - 1] == 1:
            k = find_install_year(y_conv, i, n - 1)
            Salvage_amount_conv += C_invest[i] * residual_end[i][k] * (1 / (1 + r) ** (n - 1))

    total_cost_conv = (Investment_cost_conv + Cost_of_transformer_replace_conv
                        + Cost_of_transformer_losses_conv - Salvage_amount_conv
                        + Cost_of_transformer_Outage_conv)

    breakdown = {
        "Investment cost":     Investment_cost_conv,
        "Replacement cost":    Cost_of_transformer_replace_conv,
        "No-load/load losses": Cost_of_transformer_losses_conv,
        "Outage cost":         Cost_of_transformer_Outage_conv,
        "Salvage value (-)":   Salvage_amount_conv,
        "TOTAL NPV cost":      total_cost_conv,
    }

    return total_cost_conv, breakdown, p_conv


# In[ ]:


total_cost_conv, cost_breakdown_conv, p_conv = compute_conventional_cost(
    x_conv, y_conv, z_conv, Peak_Load, Transformer_sizes, n,
    C_invest, C_replace, Emergenecy_replace_cost,
    C_electricity, k_core, k_copper, r,
    Interruption_cost_rate, Interruption_time,
    sum_sq_by_year, yearly_loss, residual_frac, residual_end,
    eta, beta
)

print("=== Conventional Method - Cost Breakdown (Net Present Value, $) ===\n")
table = PrettyTable()
table.field_names = ["Cost component", "Value ($)"]
for k_, v_ in cost_breakdown_conv.items():
    table.add_row([k_, f"{v_:,.2f}"])
print(table)

