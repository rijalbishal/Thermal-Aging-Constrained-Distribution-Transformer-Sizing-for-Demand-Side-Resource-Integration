# Thermal-Aging-Constrained Distribution Transformer Sizing for Demand-Side Resource Integration

This repository contains the Python implementation and supporting input data for the published study on Thermal-Aging-Constrained_Distribution_Transformer_Sizing_for_Demand-Side_Resource_Integration. 

The framework incorporates transformer thermal aging, load growth, electric vehicle (EV) charging, photovoltaic (PV) generation, heat pump (HP) demand, failure probability, energy losses, replacement costs, and salvage value into a multi-year planning model.

## Related Publication

**B. Rijal, X. Fang, and W. Wang**, "Thermal-Aging-Constrained Distribution Transformer Sizing for Demand-Side Resource Integration," *IEEE Open Access Journal of Power and Energy*, vol. 13, pp. 863–876, 2026.

**DOI:** [10.1109/OAJPE.2026.3733304](https://doi.org/10.1109/OAJPE.2026.3733304)

Please cite the published paper when using this repository in your research.

## 1. Research Objectives

The primary objectives of this project are to:

- Model residential DT net-load profiles under different electrification scenarios.
- Estimate transformer insulation aging using the IEEE Std. C57.91 thermal-aging model.
- Represent EV charging uncertainty using Monte Carlo simulation.
- Evaluate the effects of PV generation, HP demand, and baseline load growth.
- Formulate a mixed-integer optimization model for transformer sizing and replacement planning.
- Evaluate investment, replacement, energy-loss, outage-risk, and salvage-value costs.
- Compare optimization-based sizing with a conventional transformer-sizing approach.

## 2. Methodology

The framework consists of the following major components.

### 2.1 Load Profile Modeling

Seasonal 24-hour profiles are constructed for conventional residential demand, EV charging, PV generation, and HP demand. These profiles are combined to estimate the DT net load over the planning horizon.

### 2.2 EV Charging Model

Monte Carlo simulation represents variations in daily travel distance and charging start time. The model generates aggregate charging profiles using the assumed number of households, EV adoption levels, charger rating, battery capacity, and charging efficiency.

### 2.3 Thermal Aging Model

The IEEE Std. C57.91 thermal model is used to estimate winding hot-spot temperature and insulation aging under the projected load and ambient-temperature conditions.

### 2.4 Failure Probability

A conditional Weibull failure model represents the probability of transformer failure during a planning year, given survival until the beginning of that year. A piecewise linear (PWL) approximation is used to incorporate this relationship into the optimization framework.

### 2.5 Optimization Model

The optimization model selects transformer ratings and replacement timing over the planning horizon while accounting for investment, replacement, operating losses, expected outage consequences, and salvage value.


## 3. Input Data

The optimization implementation requires the following Excel input files.

| File | Contents |
|---|---|
| `Base_load_curve.xlsx` | Seasonal residential load profiles |
| `HP_load_profile.xlsx` | Heat pump load profile |
| `PV Output Curve Normalized Data.xlsx` | Normalized PV generation profile |
| `Hourly_Avg_Weather.xlsx` | Ambient-temperature data |

The current implementation reads these filenames directly. Therefore, place the files in the working directory from which the Python script is executed, or update the file paths in the code if the files are stored in a separate data directory.

### Input Requirements

- `Base_load_curve.xlsx` must include a worksheet named `Seasonal_loads` with the columns referenced in the code, including `residential_load`, `Winter`, `Spring`, `Summer`, and `Fall`.
- `HP_load_profile.xlsx` must include a column named `Heat_Pump`.
- `PV Output Curve Normalized Data.xlsx` must include a column named `Annual_Avg`.
- `Hourly_Avg_Weather.xlsx` must contain the weather data expected by the selected simulation configuration.

## 4. Software Requirements

The Python implementation uses:

- Python
- NumPy
- pandas
- Matplotlib
- PrettyTable
- Gurobi Optimizer and the `gurobipy` Python interface

Install the Python packages using:

```bash
pip install -r requirements.txt
```

A valid Gurobi license is required to solve the optimization model. Each user must configure their own license according to Gurobi's applicable licensing terms. License files and credentials must not be committed to this repository.

The published study reports Gurobi Optimizer version 13.0.0. The Python environment and Gurobi version should be documented and tested when preparing a reproducible release.

## 5. Running the Optimization Model

### Step 1: Obtain the repository

Clone the repository or download the source files and required input data.

### Step 2: Install the dependencies

From the repository root, run:

```bash
pip install -r requirements.txt
```

Ensure that Gurobi is installed and its license is configured correctly.

### Step 3: Check the input files

Confirm that all required Excel files are available at the paths specified in the code.

### Step 4: Run the optimization

From the repository root, execute:

```bash
python src/optimization.py
```

The script builds and solves the transformer-sizing optimization model. The current implementation reports the optimization status, transformer-selection variables, effective thermal age, failure probabilities, and cost breakdown.

The exact results depend on the input profiles, model parameters, software versions, and selected scenario.


## 6. License

The code license and reuse conditions are specified in the `LICENSE` file. Third-party datasets and external software remain subject to their respective terms and licenses.
