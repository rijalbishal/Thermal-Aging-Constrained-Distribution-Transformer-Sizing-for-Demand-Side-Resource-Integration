#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import gurobipy as gp
from gurobipy import GRB
from prettytable import PrettyTable


# In[2]:


#-------------------site recorded data for particular DT---------
n_houses = 6
Current_loading = 100                                                   # % loading in existing transformer 
Current_transformer_size = 25                                              # Current size of distribution transformer


# In[3]:


#---------------------define optimization parameters-----------------------
n=25  #planning horizon

#---------------------Load forecasting data------------
growth_rate = 0.012 #base load growth

# Year at which PV integration
Power_of_PV = 5   # Expected power of PV
PV_pen_year = 5  # Expected  PV integration year 

EV_projection1 = 0.5 # Consumer to EV ratio  first bump
EV_penetration_year = 5  #expected pv penetration year 

EV_projection2 =  1  #second bump
EV_penetration_year2 = 10 # years 

# Heat pump projected loads 

Power_of_HP = 5  # 5 kw is considered for general 5kW load

HP_bump1 = 5    # 1st targeted HP penetration year
HP_bump2 = 10   # 2nd targeted HP penetration year

HP_ratio2= 0.5   # HP Penetration level at HP_bump2 year
HP_ratio1 = 0.25 # HP Penetration level at HP_bump1 year


# In[4]:


# ---------------------- define parameters for EV----------------------
n_trials = 10000          
battery_capacity = 60      # in kWhr 
charging_power = 7.5      # In kW 
efficiency = 0.8
Lmax = 250                 # In Miles

travel_mu = 2.61     
travel_sigma = 1.32       
arrival_mu = 16            # Calulcated from NHTS data for residential loads ( exmaple:  delayed charging: 24,   commercial load: 9 )      
arrival_sigma = 4          # Calulcated from NHTS data for residential loads ( example:  delayed charging : 2.5,      commercial: 3 )


# In[5]:


# ---------- MONTE CARLO SIMULATION  ----------

def EV_calculation(Customer_to_EV_Ratio):
    n_Evs= int(n_houses * Customer_to_EV_Ratio)
    aggregate_profiles = []

    for trial in range(n_trials):
        load_profile = np.zeros(24)  

        for house in range(n_Evs):
            # Step 1: randomly select travel distance
            distance = np.random.lognormal(mean=travel_mu, sigma=travel_sigma)
            distance = min(distance, 350)

            # Step 2: Calculate initial SOC
            E0 = 0.85 - (distance / Lmax)
            E0 = np.clip(E0, 0, 0.85)

            # Step 3: Charging duration
            charging_duration = ((0.85 - E0) * battery_capacity) / (charging_power * efficiency)
            hours_needed = int(np.ceil(charging_duration))

            # Step 4: Sample arrival time
            arrival_time = int(np.clip(np.random.normal(arrival_mu, arrival_sigma), 0, 23))

            # Step 5: Schedule charging 
            hour_pointer = arrival_time
            hours_charged = 0

            while hours_charged < hours_needed:
                t = hour_pointer % 24
                load_profile[t] += charging_power
                hours_charged += 1
                hour_pointer += 1

        aggregate_profiles.append(load_profile)

    aggregate_profiles = np.array(aggregate_profiles)
    EV_load = np.percentile(aggregate_profiles, 98, axis=0)
    
    return EV_load


# In[6]:


#---------------------Read the normalized Base load Curve, HP load and PV output---------------

base_df = pd.read_excel("Base_load_curve.xlsx", sheet_name="Seasonal_loads")
base_load = base_df['residential_load'].values  #residential_load, Large_office, Flat

base_winter = base_df['Winter'].values  
base_Spring = base_df['Spring'].values  
base_Summer= base_df['Summer'].values  
base_Fall = base_df['Fall'].values

HP_df= pd.read_excel("HP_load_profile.xlsx")
HP = HP_df['Heat_Pump'].values

pv_df = pd.read_excel("PV Output Curve Normalized Data.xlsx")
pv_profile = pv_df['Annual_Avg'].values


# In[7]:


#---------------------------Net Power Calculation----------------------------

Winter_Loading = base_winter * Current_loading * Current_transformer_size/100
Spring_Loading = base_Spring * Current_loading * Current_transformer_size/100
Summer_Loading = base_Summer * Current_loading * Current_transformer_size/100
Fall_Loading   = base_Fall * Current_loading * Current_transformer_size/100

base_K_winter = np.zeros((n, 24))
base_K_spring = np.zeros((n, 24))
base_K_summer = np.zeros((n, 24))
base_K_fall   = np.zeros((n, 24))

for i in range(n):
    pv_add = n_houses* 1 *pv_profile * Power_of_PV if i >= PV_pen_year else 0

    if i >= EV_penetration_year2:
        ev_add = EV_calculation(EV_projection2)
    elif i >= EV_penetration_year:
        ev_add = EV_calculation(EV_projection1)
    else:
        ev_add = 0

    if i>= HP_bump2:
        HP_add= Power_of_HP * HP* HP_ratio2 *n_houses
    elif i>= HP_bump1:
        HP_add= Power_of_HP * HP* HP_ratio1*n_houses
    else:
        HP_add = 0
        
    base_K_winter[i] = Winter_Loading *(1 + growth_rate) ** i + ev_add - pv_add + HP_add
    base_K_spring[i] = Spring_Loading *(1 + growth_rate) ** i + ev_add - pv_add
    base_K_summer[i] = Summer_Loading*(1 + growth_rate) ** i + ev_add - pv_add
    base_K_fall[i] = Fall_Loading  *(1 + growth_rate) ** i + ev_add - pv_add

Peak_Load = np.zeros(n)
for i in range(n):
    Peak_Load[i] = Overall_Peak = np.max([
    np.max(base_K_winter[i]),
    np.max(base_K_spring[i]),
    np.max(base_K_summer[i]),
    np.max(base_K_fall[i])
])


# In[8]:


# ---------------------- define parameters of IEEE Transformer Aging Model ----------------------
rated_life_hours = 180000  
delta_theta_TO_R = 60  
delta_theta_HS_R = 20  
R = 4.87  
n_exp = 0.8  
m = 0.8  
tau_TO_R = 3.5  


# In[9]:


# ------------------- Transformer Thermal Model to calculate the Winding Hottest spot temperature ------------------
def thermal_model(K, ambient_temp):
    delta_theta_TO_R = 60
    delta_theta_HS_R = 20
    R = 4.87
    tau_TO = 3.5
    tau_w = 0.1 
    theta_H_list = []
    Ki = 0.634
    for i in range(len(K)):
        Ku = K[i]
        
        delta_theta_TO_i = delta_theta_TO_R * ((Ki**2 * R + 1) / (R + 1))
        delta_theta_TO_u = delta_theta_TO_R * ((Ku**2 * R + 1) / (R + 1))
        delta_theta_TO = delta_theta_TO_u * (1 - np.exp(-1 / tau_TO)) + delta_theta_TO_i * np.exp(-1 / tau_TO)
        
        delta_theta_H_u = delta_theta_HS_R * Ku**2
        delta_theta_H_i = delta_theta_HS_R * Ki**2
        delta_theta_H = delta_theta_H_u * (1 - np.exp(-1 / tau_w)) + delta_theta_H_i * np.exp(-1 / tau_w)
        
        theta_H = ambient_temp[i] + delta_theta_TO + delta_theta_H
        theta_H_list.append(theta_H)
        Ki = Ku
    return theta_H_list


# In[10]:


# ---------------------- define parameters of optimizer----------------------

Transformer_sizes = [15, 25, 37.5, 50, 75, 100]   # Standard DT sizes

C_invest = [3500, 3853, 4015, 4178, 5249, 6053]  # puchasing cost associated with each DT

C_electricity = 0.14   # $/kWh 
k_core = 0.01          # Iron loss factor
k_copper = 0.01        # Copper loss factor
r = 0.07               #discount factor 
Interruption_cost_rate = 4  
Interruption_time = [4,4,4,4,4,4]

Emergenecy_replace_cost = [1.1 * cost for cost in C_invest]  # Consequence of failure   
C_replace = C_invest.copy() 


# In[11]:


# # ---------------------- calculate remaining transformer life ----------------------
df=pd.read_excel('Hourly_Avg_Weather.xlsx')

#ambient_temp = df['Minnesota'].values      # For actual Minnesota temperature
#ambient_temp = df['Texas'].values          # For acutal Texas temperature
 
ambient_temp= np.full(24, 30)               # Flat 30 degree temeperature 

seasons = ['winter', 'spring', 'summer', 'fall']

base_K_by_season = {
    'winter': base_K_winter,
    'spring': base_K_spring,
    'summer': base_K_summer,
    'fall'  : base_K_fall
}

days_in_season = {
    'winter': 90,
    'spring': 92,
    'summer': 92,
    'fall'  : 91
}

def transformer_life(j, installation_year,replacement):
    cumulative_life_loss = 0.0  

    for year in range(installation_year, n):
        yearly_loss_of_life = 0.0  

        for season in seasons:
            base= np.asarray(base_K_by_season[season])
            Load_profile = base[year]

            loading_pu = (Load_profile ) / Transformer_sizes[j]
            theta_H = thermal_model(loading_pu, ambient_temp)
            
            aaf_hourly = np.exp((15000 / 383) - (15000 / (np.asarray(theta_H) + 273)))
            F_eqa = np.mean(aaf_hourly)
            
            season_days = days_in_season[season]
            seasonal_loss_of_life = (F_eqa * 24 * season_days) / rated_life_hours

            yearly_loss_of_life += seasonal_loss_of_life

        cumulative_life_loss += yearly_loss_of_life

        if replacement <= year:
            return 1-cumulative_life_loss
            break
        elif cumulative_life_loss >= 1:
            return (year) - installation_year
    
    return n - installation_year
    
def yearly_life_loss(size_idx, year):
    yearly_loss = 0.0

    for season in seasons:
        load_profile = np.asarray(base_K_by_season[season])[year]

        loading_pu = load_profile / Transformer_sizes[size_idx]
        theta_H = thermal_model(loading_pu, ambient_temp)

        aaf_hourly = np.exp((15000 / 383) - (15000 / (np.asarray(theta_H) + 273)))
        F_eqa = np.mean(aaf_hourly)

        yearly_loss += (F_eqa * days_in_season[season]) / 365

    return float(yearly_loss)   # fraction of rated life used in this year

yearly_loss = {
    (i, j): round(yearly_life_loss(i, j),4)
    for i in range(len(Transformer_sizes))
    for j in range(n)
}



# for salvage value calculation based on remaining life 
residual_frac = {}
for i in range(len(Transformer_sizes)):
    residual_frac[i] = {}
    for j in range(n):
        residual_frac[i][j] = {}
        for k in range(j+1, n):   # removal year j, install year k
            lol_pct = transformer_life(i, j, k-1)          # used until year j-1
            lol_pct = min(100.0, max(0.0, float(lol_pct))) # clamp
            residual_frac[i][j][k] = max(0.0, 1.0 - lol_pct/100.0)

residual_end = {}
for i in range(len(Transformer_sizes)):
    residual_end[i] = {}
    for j in range(n):
        lol_pct_end = transformer_life(i, j, n-1)          # used until last year
        lol_pct_end = min(100.0, max(0.0, float(lol_pct_end)))
        residual_end[i][j] = max(0.0, 1.0 - lol_pct_end/100.0)


# In[25]:


# ---------------------- Initialize and define outage probablity of the transformer ----------------------
eta= 20
beta= 4
M_age = 200.0  # maximum age of DT 


# In[13]:


# ---------------------- Initialization with gurobi ----------------------

model = gp.Model("Transformer_Sizing")   

x = model.addVars(len(Transformer_sizes), n, vtype=GRB.BINARY, name="transformeruse")  
y = model.addVars(len(Transformer_sizes), n, vtype=GRB.BINARY, name="Install")
z = model.addVars(len(Transformer_sizes), n, vtype=GRB.BINARY, name="Salvage")
w = model.addVars(len(Transformer_sizes), n, vtype=GRB.CONTINUOUS, name="Ageoftransformer")
p = model.addVars(len(Transformer_sizes), n, vtype=GRB.CONTINUOUS, name="outage_prob")
A = model.addVars(len(Transformer_sizes), n, vtype=GRB.CONTINUOUS, name="Age_After_Year")

B = model.addVars(len(Transformer_sizes), n, lb=0.0, ub=M_age, vtype=GRB.CONTINUOUS, name="Age_Before_Year")

active_prob = model.addVars(len(Transformer_sizes), n, lb=0.0, ub=1.0, vtype=GRB.CONTINUOUS, name="active_outage_prob")


I = range(len(Transformer_sizes))
K = range(n)

u_index = [(i,k,j) for i in I for k in K for j in range(k+1, n)]
u = model.addVars(u_index, vtype=GRB.BINARY, name="u")

keep = model.addVars([(i,k) for i in I for k in K], vtype=GRB.BINARY, name="keep")


# In[14]:


# ---------------------- Cost Functions ----------------------

Investment_cost = gp.quicksum(
    y[i, j] * C_invest[i] * (1 / (1 + r) ** j)
    for i in range(len(Transformer_sizes))
    for j in range(n)
)

#-------------------------------------------------------------
Cost_of_transformer_replace = gp.quicksum(
    z[i, j] *C_replace[i] * (1 / (1 + r) ** j)
    for i in range(len(Transformer_sizes))
    for j in range(n)
)

#--------------------------------------------------------------

sum_sq_by_year = np.zeros(n)
for j in range(n):
    sum_sq_by_year[j] = (
        np.sum(base_K_winter[j] ** 2) * days_in_season['winter'] +
        np.sum(base_K_spring[j] ** 2) * days_in_season['spring'] +
        np.sum(base_K_summer[j] ** 2) * days_in_season['summer'] +
        np.sum(base_K_fall[j]   ** 2) * days_in_season['fall']
    )

Cost_of_transformer_losses = gp.quicksum(
    x[i, j] * (
        k_core * Transformer_sizes[i] * 8760  * C_electricity +
        k_copper *  (sum_sq_by_year[j]/ Transformer_sizes[i]) * C_electricity
    ) * (1 / (1 + r) ** j)
    for i in range(len(Transformer_sizes))
    for j in range(n)
)

#---------------------------------------------------------------
Cost_of_transformer_Outage = gp.quicksum(
    p[i, j] * x[i,j]*
    ( Peak_Load[j] * Interruption_time[i] * C_electricity +
        Peak_Load[j] * Interruption_cost_rate +
        Emergenecy_replace_cost[i]
    ) * (1 / (1 + r) ** j)
    for i in range(len(Transformer_sizes))
    for j in range(n)
)

#-------------------------------------------------------------
Salvage_amount = gp.quicksum(
    C_invest[i] * residual_frac[i][k][j] * u[i,k,j] * (1 / (1 + r) ** j)
    for i in I
    for k in K
    for j in range(k+1, n)
) + gp.quicksum(
    C_invest[i] * residual_end[i][k] * keep[i,k] * (1 / (1 + r) ** (n-1))
    for i in I
    for k in K
)

#----------------------------------------------------
total_cost = Investment_cost +  Cost_of_transformer_replace + Cost_of_transformer_losses - Salvage_amount + Cost_of_transformer_Outage      

model.setObjective(total_cost, GRB.MINIMIZE)


# In[15]:


# ================================================================
# CONSTRAINT 1: At least one transformer must be active each period
# ================================================================
for j in range(n):
    model.addConstr(
        gp.quicksum(x[i, j] for i in range(len(Transformer_sizes))) >= 1,
        name=f"min_one_transformer_{j}"
    )
          
# ================================================================
# CONSTRAINT 2: Installation Logic
#  WHEN TRANSFORMER TRANSITIONS FROM UNUSED TO USED
# ================================================================
for i in range(len(Transformer_sizes)):
    model.addConstr(y[i, 0] == x[i, 0],                    name=f"install_init_{i}")

    for j in range(1, n):
        model.addConstr(y[i, j] >= x[i, j] - x[i, j-1],   name=f"install_lb_{i}_{j}")
        model.addConstr(y[i, j] <= x[i, j],                name=f"install_ub1_{i}_{j}")
        model.addConstr(y[i, j] <= 1 - x[i, j-1],         name=f"install_ub2_{i}_{j}")

# ================================================================
# CONSTRAINT 3: Salvage/Removal Logic
# WHEN TRANSFORMER TRANSITIONS FROM USED TO UNUSED
# ================================================================
for i in range(len(Transformer_sizes)):
    model.addConstr(z[i, 0] == 0,                    name=f"salvage_init_{i}")

    for j in range(1, n):
        model.addConstr(z[i, j] >= x[i, j-1] - x[i, j],   name=f"salvage_lb_{i}_{j}")
        model.addConstr(z[i, j] <= x[i, j-1],              name=f"salvage_ub1_{i}_{j}")
        model.addConstr(z[i, j] <= 1 - x[i, j],            name=f"salvage_ub2_{i}_{j}")
        
# ================================================================
# CONSTRAINT 4: Thermal age
# Accumulation constraint
# ================================================================

BigM = {}
for i in range(len(Transformer_sizes)):
    cumulative_loss = 0
    for j in range(n):
        cumulative_loss += yearly_loss[i, j]
        BigM[i, j] = cumulative_loss

for i in range(len(Transformer_sizes)):

    # Initial year
    model.addConstr(
        A[i, 0] == yearly_loss[i, 0],
        name=f"AgeInit_{i}"
    )

    model.addConstr(
        w[i, 0] <= BigM[i, 0] * x[i, 0],
        name=f"BigM1_{i}_0"
    )
    model.addConstr(
        w[i, 0] <= A[i, 0],
        name=f"BigM2_{i}_0"
    )
    model.addConstr(
        w[i, 0] >= A[i, 0] - BigM[i, 0] * (1 - x[i, 0]),
        name=f"BigM3_{i}_0"
    )
    model.addConstr(
        w[i, 0] >= 0,
        name=f"BigM4_{i}_0"
    )

    # Remaining years
    for j in range(1, n):

        model.addConstr(
            A[i, j] == w[i, j - 1] + yearly_loss[i, j],
            name=f"AccumulatedAge_{i}_{j}"
        )

        model.addConstr(
            w[i, j] <= BigM[i, j] * x[i, j],
            name=f"BigM1_{i}_{j}"
        )
        model.addConstr(
            w[i, j] <= A[i, j],
            name=f"BigM2_{i}_{j}"
        )
        model.addConstr(
            w[i, j] >= A[i, j] - BigM[i, j] * (1 - x[i, j]),
            name=f"BigM3_{i}_{j}"
        )
        model.addConstr(
            w[i, j] >= 0,
            name=f"BigM4_{i}_{j}"
        )

# ================================================================
# CONSTRAINT 5: Failure probablity mapping constraint
# p[i,j] = 1 - exp(-[((A[i,j]/eta)^beta)
#                    - (((A[i,j]-yearly_loss[i,j])/eta)^beta)])
#
# A[i,j] = w[i,j-1] + yearly_loss[i,j]
# A[i,j] is the end-of-year cumulative age before reset
# ================================================================

P_SAT = 0.999999          # probability saturation threshold
MAX_PWL_POINTS = 80       # maximum number of PWL points per constraint
MIN_RANGE = 1e-6          # numerical tolerance


def cond_failure_prob(tau_end, ell, eta, beta):
    tau_start = max(tau_end - ell, 0.0)

    exponent = (tau_end / eta) ** beta - (tau_start / eta) ** beta

    # numerical safety
    if exponent >= 50:
        return 1.0

    prob = 1.0 - np.exp(-exponent)
    return min(max(prob, 0.0), 1.0)


def build_conditional_pwl_points(ell, x_max, eta, beta):
    x_min = max(float(ell), 0.0)
    x_max = max(float(x_max), x_min)

    # If the variable range is essentially fixed, no PWL is needed
    if x_max - x_min <= MIN_RANGE:
        p_fixed = cond_failure_prob(x_min, ell, eta, beta)
        return None, None, p_fixed

    p_min = cond_failure_prob(x_min, ell, eta, beta)
    p_max = cond_failure_prob(x_max, ell, eta, beta)

    # Case 1: probability is already saturated at the lower bound
    if p_min >= P_SAT:
        pwl_x = [x_min, x_max]
        pwl_y = [p_min, p_min]
        return pwl_x, pwl_y, None

    # Case 2: probability does not saturate over the full range
    if p_max < P_SAT:
        pwl_x = np.linspace(x_min, x_max, MAX_PWL_POINTS).tolist()
        pwl_y = [cond_failure_prob(x, ell, eta, beta) for x in pwl_x]
        return pwl_x, pwl_y, None

    # Case 3: probability saturates somewhere between x_min and x_max
    # Find saturation point using binary search
    lo = x_min
    hi = x_max

    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if cond_failure_prob(mid, ell, eta, beta) >= P_SAT:
            hi = mid
        else:
            lo = mid

    x_sat = hi

    # Use most points before saturation, then one final point at x_max
    pwl_x = np.linspace(x_min, x_sat, MAX_PWL_POINTS - 1).tolist()

    if x_max > x_sat + MIN_RANGE:
        pwl_x.append(x_max)

    # remove possible duplicates
    pwl_x = sorted(set([round(x, 10) for x in pwl_x]))

    pwl_y = [cond_failure_prob(x, ell, eta, beta) for x in pwl_x]

    return pwl_x, pwl_y, None


for i in range(len(Transformer_sizes)):
    for j in range(n):

        ell_ij = float(yearly_loss[i, j])
        x_max = float(BigM[i, j])

        pwl_x_ij, pwl_y_ij, p_fixed = build_conditional_pwl_points(
            ell_ij,
            x_max,
            eta,
            beta
        )

        # If A[i,j] is fixed, directly set p[i,j]
        if p_fixed is not None:
            model.addConstr(
                p[i, j] == p_fixed,
                name=f"conditional_failure_prob_fixed_{i}_{j}"
            )

        else:
            model.addGenConstrPWL(
                A[i, j],
                p[i, j],
                pwl_x_ij,
                pwl_y_ij,
                name=f"conditional_failure_prob_{i}_{j}"
            )

           
# ================================================================
# CONSTRAINT 6: Installation- Removal linkage
# To count correct installation removal pair 
# ================================================================
for i in I:
    for k in K:
        model.addConstr(
            gp.quicksum(u[i,k,j] for j in range(k+1, n)) + keep[i,k] == y[i,k],
            name=f"link_install_{i}_{k}"
        )
for i in I:
    for j in range(n):
        model.addConstr(
            gp.quicksum(u[i,k,j] for k in range(0, j)) == z[i,j],
            name=f"link_remove_{i}_{j}"
        )


# In[28]:


# ---------------------- Solve the model ----------------------
model.optimize()

# ---------------------- Print the result ----------------------
status = model.status
if status == GRB.OPTIMAL:
    print("Optimal solution found!")
else:
    print("Model is infeasible.")


# In[18]:


# ---------------------- plot the Gurobi Variables in Table ----------------------
def print_variable_table(var, var_name, binary=True, threshold=0.01):
    print(f"\n📋 {var_name.upper()} Table:")
    table = PrettyTable()
    table.field_names = ["Year"] + [f"{Transformer_sizes[i]} kVA" for i in range(len(Transformer_sizes))]

    for j in range(n):
        row = [f"Year {j}"]
        for i in range(len(Transformer_sizes)):
            val = var[i, j].X
            if binary:
                row.append("✓" if val > 0.5 else "")
            else:
                row.append(f"{val:.2f}" if val > threshold else "")
        table.add_row(row)
    print(table)

if model.status == GRB.OPTIMAL:
    print_variable_table(x, "x (transformer use)", binary=True)
    print_variable_table(y, "y (installation)", binary=True)
    print_variable_table(z, "z (removal)", binary=True)
    print_variable_table(w, "w (effective age)", binary=False)
    print_variable_table(p, "p (outage probability)", binary=False)
else:
    print("Model is not optimal, skipping variable table print.")


# In[20]:


if model.status == GRB.OPTIMAL:
    
    # ── Get each component value directly from Gurobi expressions ──
    inv_cost    = Investment_cost.getValue()
    rep_cost    = Cost_of_transformer_replace.getValue()
    loss_cost   = Cost_of_transformer_losses.getValue()
    outage_cost = Cost_of_transformer_Outage.getValue()
    salvage     = Salvage_amount.getValue()
    total       = total_cost.getValue()

    # ── Print breakdown ──
    gross       = inv_cost + rep_cost + loss_cost #+ outage_cost

    print("\n" + "="*55)
    print(f"{'TRANSFORMER COST BREAKDOWN':^55}")
    print("="*55)
    print(f"{'Cost Component':<30} {'Amount ($)':>15} {'Share (%)':>8}")
    print("-"*55)
    print(f"{'Investment Cost':<30} ${inv_cost:>13,.2f} {inv_cost/gross*100:>7.1f}%")
    print(f"{'Replacement Cost':<30} ${rep_cost:>13,.2f} {rep_cost/gross*100:>7.1f}%")
    print(f"{'Energy Loss Cost':<30} ${loss_cost:>13,.2f} {loss_cost/gross*100:>7.1f}%")
    print(f"{'Outage Cost':<30} ${outage_cost:>13,.2f} {outage_cost/gross*100:>7.1f}%")
    print(f"{'Salvage Value':<30} -${salvage:>12,.2f} -{salvage/gross*100:>6.1f}%")
    print("-"*55)
    print(f"{'TOTAL COST':<30} ${total:>13,.2f}")
    print("="*55)
    print(f"\n  Gurobi Objective Value : ${model.ObjVal:,.2f}")
    print(f"  Difference             : ${abs(model.ObjVal - total):,.2f}")
    print("="*55)

