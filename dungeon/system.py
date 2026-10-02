"""
pairwise-dungeon-system - DungeonSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class DungeonSystem:
    def __init__(self):
        self.state = {}

    def match_dungeon(self, *args, **kwargs):
        """BUG: 副本匹配不做职业搭配，五个输出没治疗进本就灭"""
        return None

    def scale_difficulty(self, *args, **kwargs):
        """BUG: 难度缩放只加血量，不加减伤和伤害"""
        return None

    def update_boss_phase(self, *args, **kwargs):
        """BUG: BOSS阶段不做转换条件，血量到了不转阶段"""
        return None

    def roll_loot(self, *args, **kwargs):
        """BUG: 掉落ROLL不做需求优先级，所有人都能需求"""
        return None

    def update_dungeon_timer(self, *args, **kwargs):
        """BUG: 副本计时不做暂停，掉线了时间还在走"""
        return None

