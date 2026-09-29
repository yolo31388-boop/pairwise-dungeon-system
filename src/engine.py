"""副本地下城 - 带7个bug"""
from dataclasses import dataclass, field
import time

@dataclass
class DungeonRun:
    rid: str
    difficulty: str
    players: list
    start_time: float
    deaths: int = 0
    revive_coins: int = 0
    damage_taken: int = 0

class DungeonSystem:
    def __init__(self):
        self.runs: dict[str, DungeonRun] = {}
        self.weekly_clear: dict[str, int] = {}
        self.weekly_reset_day = 1  # bug7: 自然日重置

    def apply_difficulty(self, base_hp, difficulty):
        # bug1: 难度不影响属性
        return base_hp

    def match(self, players):
        # bug2: 只看等级
        return True

    def get_remaining_time(self, run_id, current_time):
        # bug3: 用本地时间
        run = self.runs[run_id]
        return current_time - run.start_time

    def calc_score(self, run_id):
        run = self.runs[run_id]
        # bug4: 只看时间
        return 10000 / max(1, run.deaths + 1)

    def distribute_loot(self, run_id, items):
        # bug5: 自由拾取
        return {self.runs[run_id].players[0]: items}

    def quit_run(self, run_id, player):
        # bug6: 无惩罚
        self.runs[run_id].players.remove(player)
        return True

    def can_enter(self, player_id, current_day):
        # bug7: 自然日
        if self.weekly_clear.get(player_id, 0) >= 3:
            return False
        return True
