"""副本地下城系统 - 修复版

修复的 7 个问题:
1. 难度真实影响怪物属性与掉落倍率, 且配置化
2. 匹配同时校验等级区间与装备评分区间
3. 计时使用单调时钟(服务器侧), 修改本地时间无效
4. 评分综合通关时间/死亡次数/复活币/受击
5. 掉落分配支持 需求/贪婪/自由 三种模式, 带 roll 点
6. 中途退出有冷却惩罚并记录逃跑率
7. 每周次数按固定重置时间点(默认周二凌晨4点)计算
"""
from dataclasses import dataclass
import random
import time

DEFAULT_DIFFICULTY_CONFIG = {
    "normal": {"hp_mult": 1.0, "attack_mult": 1.0, "loot_mult": 1.0},
    "hard":   {"hp_mult": 1.5, "attack_mult": 1.5, "loot_mult": 1.5},
    "hell":   {"hp_mult": 2.2, "attack_mult": 2.0, "loot_mult": 2.5},
}

LOOT_MODES = ("need", "greed", "free")

SECONDS_PER_DAY = 86400
SECONDS_PER_WEEK = 7 * SECONDS_PER_DAY


@dataclass
class DungeonRun:
    rid: str
    difficulty: str
    players: list
    start_time: float
    deaths: int = 0
    revive_coins: int = 0
    damage_taken: int = 0
    hits_taken: int = 0
    clear_time: float | None = None
    start_monotonic: float | None = None  # 由 DungeonSystem 用系统时钟盖章


class DungeonSystem:
    WEEKLY_CLEAR_LIMIT = 3

    def __init__(self, difficulty_config=None, level_spread=5, gear_score_spread=200,
                 quit_cooldown=300.0, reset_weekday=1, reset_hour=4,
                 time_limit=1800.0, clock=time.monotonic, rng=None):
        # difficulty_config: {name: {"hp_mult":, "attack_mult":, "loot_mult":}}
        self.difficulty_config = difficulty_config or dict(DEFAULT_DIFFICULTY_CONFIG)
        self.level_spread = level_spread            # 匹配允许的最大等级差
        self.gear_score_spread = gear_score_spread  # 匹配允许的最大装备评分差
        self.quit_cooldown = quit_cooldown          # 中途退出冷却秒数
        self.reset_weekday = reset_weekday          # 周重置星期(周一=0, 默认周二)
        self.reset_hour = reset_hour                # 周重置小时(默认凌晨4点)
        self.time_limit = time_limit                # 副本时限(秒)
        self._clock = clock                         # 单调时钟, 不受本地时间修改影响
        self._rng = rng or random.Random()

        self.runs: dict[str, DungeonRun] = {}
        self.weekly_clear: dict[tuple, int] = {}    # (player_id, period_key) -> 次数
        self.quit_cooldowns: dict[str, float] = {}  # player -> 冷却结束时刻(单调时钟)
        self.escape_counts: dict[str, int] = {}
        self.total_runs: dict[str, int] = {}

    def _elapsed(self, run):
        if run.start_monotonic is None:
            run.start_monotonic = self._clock()
        return self._clock() - run.start_monotonic

    def start_run(self, run):
        """登记副本并用系统单调时钟盖章开始时间。"""
        run.start_monotonic = self._clock()
        self.runs[run.rid] = run
        return run

    # ---- bug1: 难度配置 ----
    def _difficulty(self, difficulty):
        try:
            return self.difficulty_config[difficulty]
        except KeyError:
            raise ValueError(f"未知难度: {difficulty!r}") from None

    def apply_difficulty(self, base_hp, difficulty):
        return int(base_hp * self._difficulty(difficulty)["hp_mult"])

    def apply_attack(self, base_attack, difficulty):
        return int(base_attack * self._difficulty(difficulty)["attack_mult"])

    def loot_multiplier(self, difficulty):
        return self._difficulty(difficulty)["loot_mult"]

    # ---- bug2: 匹配看等级 + 装备评分 ----
    @staticmethod
    def _stat(player, name):
        if isinstance(player, dict):
            return player.get(name, 0)
        return getattr(player, name, 0)

    def match(self, players):
        if len(players) < 2:
            return True
        levels = [self._stat(p, "level") for p in players]
        gears = [self._stat(p, "gear_score") for p in players]
        if max(levels) - min(levels) > self.level_spread:
            return False
        if max(gears) - min(gears) > self.gear_score_spread:
            return False
        return True

    # ---- bug3: 计时用单调时钟, current_time(本地时间)仅作兼容参数, 不参与计算 ----
    def get_remaining_time(self, run_id, current_time=None):
        run = self.runs[run_id]
        return max(0.0, self.time_limit - self._elapsed(run))

    # ---- bug4: 综合评分 ----
    def calc_score(self, run_id):
        run = self.runs[run_id]
        clear_time = run.clear_time
        if clear_time is None:
            clear_time = self._elapsed(run)
        score = 10000.0
        score -= clear_time * 5.0          # 通关时间
        score -= run.deaths * 500.0        # 死亡次数
        score -= run.revive_coins * 300.0  # 复活币
        score -= run.hits_taken * 10.0     # 受击次数
        score -= run.damage_taken * 0.01   # 承受伤害
        return max(0.0, score)

    # ---- bug5: 掉落分配 需求/贪婪/自由 + roll点 ----
    def distribute_loot(self, run_id, items, mode="free", need_players=None):
        if mode not in LOOT_MODES:
            raise ValueError(f"未知分配模式: {mode!r}, 支持 {LOOT_MODES}")
        run = self.runs[run_id]
        result = {p: [] for p in run.players}
        if mode == "free":  # 自由拾取: 先到先得
            if items and run.players:
                result[run.players[0]] = list(items)
            return result
        for item in items:
            candidates = list(run.players)
            if mode == "need":
                wanted = [p for p in candidates
                          if need_players is None or p in need_players]
                if wanted:
                    candidates = wanted
            rolls = {p: self._rng.randint(1, 100) for p in candidates}
            winner = max(candidates, key=lambda p: rolls[p])
            result[winner].append(item)
        return result

    # ---- bug6: 中途退出惩罚 ----
    def join_run(self, player):
        self.total_runs[player] = self.total_runs.get(player, 0) + 1

    def quit_run(self, run_id, player):
        run = self.runs[run_id]
        if player in run.players:
            run.players.remove(player)
        self.escape_counts[player] = self.escape_counts.get(player, 0) + 1
        self.quit_cooldowns[player] = self._clock() + self.quit_cooldown
        return True

    def can_queue(self, player):
        return self._clock() >= self.quit_cooldowns.get(player, 0.0)

    def escape_rate(self, player):
        total = self.total_runs.get(player, 0)
        if total == 0:
            return 0.0
        return self.escape_counts.get(player, 0) / total

    # ---- bug7: 固定重置时间点的周次数 ----
    def _period_key(self, timestamp):
        """返回 timestamp 所属周期的重置时刻(默认每周二凌晨4点)。"""
        lt = time.localtime(timestamp)
        days_since_reset = (lt.tm_wday - self.reset_weekday) % 7
        reset_today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday,
                                   self.reset_hour, 0, 0,
                                   lt.tm_wday, lt.tm_yday, lt.tm_isdst))
        period_start = reset_today - days_since_reset * SECONDS_PER_DAY
        if period_start > timestamp:
            period_start -= SECONDS_PER_WEEK
        return int(period_start)

    def can_enter(self, player_id, current_time):
        period = self._period_key(current_time)
        used = self.weekly_clear.get((player_id, period), 0)
        return used < self.WEEKLY_CLEAR_LIMIT

    def record_clear(self, player_id, current_time):
        period = self._period_key(current_time)
        key = (player_id, period)
        self.weekly_clear[key] = self.weekly_clear.get(key, 0) + 1
