#!/usr/bin/env python3
"""Compare multi-stage FTMO capital policies (Plan B→D vs B→E→D)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_capital_plan_sim import (  # noqa: E402
    load_eval_runs,
    load_funded_runs,
    sample_eval,
    sample_funded_monthly,
)


HORIZON_MONTHS = 12
SIMULATIONS = 20_000
BASE_SEED = 4242
INITIAL_BANKROLL = 600.0


@dataclass
class PlanConfig:
    name: str
    mode: str = "BASIC"  # or PLAN_D
    evals_per_wave: int = 4
    waves_per_month: int = 1
    feeder_fee: float = 50.0
    large_fee: float = 350.0
    risk_budget_fraction: float = 0.7
    reinvest_fraction: float = 0.5
    stage2_trigger: float = 10_000.0
    stage1_limit: float = 6.0
    large_fraction: float = 0.5


@dataclass
class PlanState:
    config: PlanConfig
    horizon: int
    bankroll: float = 0.0
    active: bool = False
    start_month: int = 0
    stage2_active: bool = False
    months_running: float = 0.0
    total_withdrawn: float = 0.0
    withdraw_schedule: np.ndarray = field(init=False)
    reinvest_schedule: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.withdraw_schedule = np.zeros(self.horizon)
        self.reinvest_schedule = np.zeros(self.horizon)


def activate_plan(plan: PlanState, bankroll: float, month: int) -> None:
    plan.bankroll = bankroll
    plan.active = True
    plan.start_month = month
    plan.stage2_active = False
    plan.months_running = 0.0
    plan.total_withdrawn = 0.0
    plan.withdraw_schedule.fill(0.0)
    plan.reinvest_schedule.fill(0.0)


def run_plan_month(
    plan: PlanState,
    month: int,
    horizon: int,
    rng: np.random.Generator,
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
) -> None:
    cfg = plan.config
    for wave_idx in range(cfg.waves_per_month):
        wave_time = month + wave_idx / max(1, cfg.waves_per_month)
        feeder_count = cfg.evals_per_wave
        large_count = 0
        if cfg.mode == "PLAN_D":
            if not plan.stage2_active:
                if plan.total_withdrawn >= cfg.stage2_trigger or plan.months_running >= cfg.stage1_limit:
                    plan.stage2_active = True
            large_fraction = cfg.large_fraction if plan.stage2_active else 0.0
            large_count = int(round(cfg.evals_per_wave * large_fraction))
            large_count = max(0, min(large_count, cfg.evals_per_wave))
            feeder_count = cfg.evals_per_wave - large_count
            if feeder_count + large_count == 0:
                feeder_count = cfg.evals_per_wave
                large_count = 0
            wave_cost = feeder_count * cfg.feeder_fee + large_count * cfg.large_fee
        else:
            wave_cost = feeder_count * cfg.feeder_fee

        max_spend = cfg.risk_budget_fraction * plan.bankroll
        if wave_cost > plan.bankroll or wave_cost > max_spend:
            continue

        plan.bankroll -= wave_cost

        for _ in range(feeder_count + large_count):
            _schedule_eval_payouts(plan, wave_time, horizon, rng, eval_df, funded_df)


def _schedule_eval_payouts(
    plan: PlanState,
    wave_time: float,
    horizon: int,
    rng: np.random.Generator,
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
) -> None:
    passed, duration_days = sample_eval(eval_df, rng)
    if not passed:
        return
    finish_time = wave_time + duration_days / 21.0
    finish_month = int(finish_time)
    if finish_month >= horizon:
        return
    series = sample_funded_monthly(funded_df, rng)
    for offset, amount in enumerate(series):
        if amount <= 0:
            continue
        event_month = finish_month + offset
        if event_month >= horizon:
            break
        withdraw_amount = amount * (1.0 - plan.config.reinvest_fraction)
        reinvest_amount = amount * plan.config.reinvest_fraction
        plan.withdraw_schedule[event_month] += withdraw_amount
        plan.reinvest_schedule[event_month] += reinvest_amount


def build_policy_bd(horizon: int) -> tuple[Callable[[], Dict[str, PlanState]], Callable[[Dict[str, PlanState], float, int], float]]:
    def factory() -> Dict[str, PlanState]:
        plan_b = PlanState(
            plan_config_b,
            horizon,
            bankroll=INITIAL_BANKROLL,
            active=True,
            start_month=0,
        )
        plan_d = PlanState(plan_config_d_direct, horizon)
        return {"B": plan_b, "D": plan_d}

    def trigger(plans: Dict[str, PlanState], profit_pool: float, month: int) -> float:
        plan_b = plans["B"]
        plan_d = plans["D"]
        if (
            not plan_d.active
            and plan_b.total_withdrawn >= 10_000.0
            and profit_pool >= 5_000.0
            and month < HORIZON_MONTHS
        ):
            profit_pool -= 5_000.0
            activate_plan(plan_d, 5_000.0, month)
        return profit_pool

    return factory, trigger


def build_policy_bed(horizon: int) -> tuple[Callable[[], Dict[str, PlanState]], Callable[[Dict[str, PlanState], float, int], float]]:
    def factory() -> Dict[str, PlanState]:
        plan_b = PlanState(plan_config_b, horizon, bankroll=INITIAL_BANKROLL, active=True, start_month=0)
        plan_e = PlanState(plan_config_e, horizon)
        plan_d = PlanState(plan_config_d_direct, horizon)
        return {"B": plan_b, "E": plan_e, "D": plan_d}

    def trigger(plans: Dict[str, PlanState], profit_pool: float, month: int) -> float:
        plan_b = plans["B"]
        plan_e = plans["E"]
        plan_d = plans["D"]
        if (
            not plan_e.active
            and plan_b.total_withdrawn >= 10_000.0
            and profit_pool >= 1_500.0
            and month < HORIZON_MONTHS
        ):
            profit_pool -= 1_500.0
            activate_plan(plan_e, 1_500.0, month)
        combined = plan_b.total_withdrawn + (plan_e.total_withdrawn if plan_e.active else 0.0)
        if (
            not plan_d.active
            and combined >= 25_000.0
            and profit_pool >= 5_000.0
            and month < HORIZON_MONTHS
        ):
            profit_pool -= 5_000.0
            activate_plan(plan_d, 5_000.0, month)
        return profit_pool

    return factory, trigger


def simulate_policy(
    policy_name: str,
    factory: Callable[[], Dict[str, PlanState]],
    trigger_fn: Callable[[Dict[str, PlanState], float, int], float],
    eval_df: pd.DataFrame,
    funded_df: pd.DataFrame,
) -> tuple[dict, pd.DataFrame]:
    total_payouts = np.zeros(SIMULATIONS)
    final_bankrolls = np.zeros(SIMULATIONS)
    net_loss_flags = np.zeros(SIMULATIONS, dtype=bool)
    bankroll_zero_flags = np.zeros(SIMULATIONS, dtype=bool)
    first5k = np.full(SIMULATIONS, np.nan)
    first10k = np.full(SIMULATIONS, np.nan)

    master_rng = np.random.default_rng(BASE_SEED)

    for sim in range(SIMULATIONS):
        plans = factory()
        profit_pool = 0.0
        cumulative = 0.0
        zero_flag = False
        run_seed = master_rng.integers(0, 2**32 - 1)
        rng = np.random.default_rng(int(run_seed))

        for month in range(HORIZON_MONTHS):
            # Apply scheduled withdrawals / reinvestments first
            for plan in plans.values():
                if not plan.active:
                    continue
                withdraw_amt = plan.withdraw_schedule[month]
                if withdraw_amt:
                    profit_pool += withdraw_amt
                    plan.total_withdrawn += withdraw_amt
                    cumulative += withdraw_amt
                    plan.withdraw_schedule[month] = 0.0
                reinvest_amt = plan.reinvest_schedule[month]
                if reinvest_amt:
                    plan.bankroll += reinvest_amt
                    plan.reinvest_schedule[month] = 0.0

            if cumulative >= 5_000.0 and np.isnan(first5k[sim]):
                first5k[sim] = month + 1
            if cumulative >= 10_000.0 and np.isnan(first10k[sim]):
                first10k[sim] = month + 1

            profit_pool = trigger_fn(plans, profit_pool, month)

            for plan in plans.values():
                if not plan.active:
                    continue
                plan.months_running += 1.0
                run_plan_month(plan, month, HORIZON_MONTHS, rng, eval_df, funded_df)

            total_liquid = profit_pool + sum(plan.bankroll for plan in plans.values() if plan.active)
            if total_liquid <= 1e-9 and month < HORIZON_MONTHS - 1:
                zero_flag = True

        total_payouts[sim] = cumulative
        final_bankrolls[sim] = profit_pool + sum(plan.bankroll for plan in plans.values() if plan.active)
        net_loss_flags[sim] = cumulative < INITIAL_BANKROLL
        bankroll_zero_flags[sim] = zero_flag or final_bankrolls[sim] <= 1e-9

    summary = {
        "policy": policy_name,
        "months": HORIZON_MONTHS,
        "simulations": SIMULATIONS,
        "mean_total_payout": float(np.mean(total_payouts)),
        "median_total_payout": float(np.median(total_payouts)),
        "p10_total_payout": float(np.percentile(total_payouts, 10)),
        "p90_total_payout": float(np.percentile(total_payouts, 90)),
        "prob_total_ge_10k": float(np.mean(total_payouts >= 10_000.0)),
        "prob_total_ge_50k": float(np.mean(total_payouts >= 50_000.0)),
        "prob_total_ge_100k": float(np.mean(total_payouts >= 100_000.0)),
        "prob_net_loss": float(np.mean(net_loss_flags)),
        "prob_bankroll_zero": float(np.mean(bankroll_zero_flags)),
        "mean_months_to_5k": float(np.nanmean(first5k)),
        "median_months_to_5k": float(np.nanmedian(first5k)),
        "mean_months_to_10k": float(np.nanmean(first10k)),
        "median_months_to_10k": float(np.nanmedian(first10k)),
        "mean_final_bankroll": float(np.mean(final_bankrolls)),
        "median_final_bankroll": float(np.median(final_bankrolls)),
    }

    per_run = pd.DataFrame(
        {
            "total_payout": total_payouts,
            "final_bankroll": final_bankrolls,
            "net_loss": net_loss_flags,
            "bankroll_zero": bankroll_zero_flags,
            "months_to_5k": first5k,
            "months_to_10k": first10k,
        }
    )

    return summary, per_run


plan_config_b = PlanConfig(name="PLAN_B", mode="BASIC", evals_per_wave=4, waves_per_month=1, feeder_fee=50.0)
plan_config_e = PlanConfig(
    name="PLAN_E",
    mode="PLAN_D",
    evals_per_wave=4,
    waves_per_month=2,
    feeder_fee=50.0,
    large_fee=350.0,
    stage2_trigger=10_000.0,
    stage1_limit=6.0,
    large_fraction=0.5,
)
plan_config_d_direct = PlanConfig(
    name="PLAN_D",
    mode="PLAN_D",
    evals_per_wave=6,
    waves_per_month=2,
    feeder_fee=50.0,
    large_fee=350.0,
    stage2_trigger=0.0,
    stage1_limit=0.0,
    large_fraction=0.5,
)


def build_policy_be3(horizon: int) -> tuple[Callable[[], Dict[str, PlanState]], Callable[[Dict[str, PlanState], float, int], float]]:
    """Plan BE3 Early promotion: B -> E at 6.5k, D at 15k."""

    def factory() -> Dict[str, PlanState]:
        plan_b = PlanState(plan_config_b, horizon, bankroll=INITIAL_BANKROLL, active=True, start_month=0)
        plan_e = PlanState(plan_config_e, horizon)
        plan_d = PlanState(plan_config_d_direct, horizon)
        return {"B": plan_b, "E": plan_e, "D": plan_d}

    def trigger(plans: Dict[str, PlanState], profit_pool: float, month: int) -> float:
        plan_b = plans["B"]
        plan_e = plans["E"]
        plan_d = plans["D"]
        if (
            not plan_e.active
            and plan_b.total_withdrawn >= 6_500.0
            and profit_pool >= 1_500.0
            and month < HORIZON_MONTHS
        ):
            profit_pool -= 1_500.0
            activate_plan(plan_e, 1_500.0, month)
        combined = plan_b.total_withdrawn + (plan_e.total_withdrawn if plan_e.active else 0.0)
        if (
            not plan_d.active
            and combined >= 15_000.0
            and profit_pool >= 5_000.0
            and month < HORIZON_MONTHS
        ):
            profit_pool -= 5_000.0
            activate_plan(plan_d, 5_000.0, month)
        return profit_pool

    return factory, trigger


def main() -> int:
    eval_df = load_eval_runs(Path("results/minimal_ftmo_eval_runs.csv"))
    funded_df = load_funded_runs(Path("results/funded_payout_ftmo_12m_runs.csv"), HORIZON_MONTHS)

    factory_bd, trigger_bd = build_policy_bd(HORIZON_MONTHS)
    summary_bd, runs_bd = simulate_policy("PLAN_BD_DIRECT", factory_bd, trigger_bd, eval_df, funded_df)
    out_summary_bd = Path("results/capital_plan_ftmo_plan_bd_direct_12m_summary.json")
    out_runs_bd = Path("results/capital_plan_ftmo_plan_bd_direct_12m_runs.csv")
    out_summary_bd.write_text(json.dumps(summary_bd, indent=2))
    runs_bd.to_csv(out_runs_bd, index=False)

    factory_bed, trigger_bed = build_policy_bed(HORIZON_MONTHS)
    summary_bed, runs_bed = simulate_policy("PLAN_BED_LADDER", factory_bed, trigger_bed, eval_df, funded_df)
    out_summary_bed = Path("results/capital_plan_ftmo_plan_bed_ladder_12m_summary.json")
    out_runs_bed = Path("results/capital_plan_ftmo_plan_bed_ladder_12m_runs.csv")
    out_summary_bed.write_text(json.dumps(summary_bed, indent=2))
    runs_bed.to_csv(out_runs_bed, index=False)

    factory_be3, trigger_be3 = build_policy_be3(HORIZON_MONTHS)
    summary_be3, runs_be3 = simulate_policy("PLAN_BE3_EARLY", factory_be3, trigger_be3, eval_df, funded_df)
    out_summary_be3 = Path("results/capital_plan_ftmo_plan_be3_early_12m_summary.json")
    out_runs_be3 = Path("results/capital_plan_ftmo_plan_be3_early_12m_runs.csv")
    out_summary_be3.write_text(json.dumps(summary_be3, indent=2))
    runs_be3.to_csv(out_runs_be3, index=False)

    comparison = {
        "PLAN_BD_DIRECT": summary_bd,
        "PLAN_BED_LADDER": summary_bed,
        "PLAN_BE3_EARLY": summary_be3,
    }
    Path("results/capital_plan_ftmo_policy_compare.json").write_text(json.dumps(comparison, indent=2))
    print("Saved policy comparison artifacts:")
    print(f"  {out_summary_bd}")
    print(f"  {out_runs_bd}")
    print(f"  {out_summary_bed}")
    print(f"  {out_runs_bed}")
    print(f"  {out_summary_be3}")
    print(f"  {out_runs_be3}")
    print("  results/capital_plan_ftmo_policy_compare.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
