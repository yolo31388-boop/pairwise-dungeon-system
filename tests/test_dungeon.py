import pytest
from dungeon.system import DungeonSystem


class TestDungeonSystem:

    def test_match_dungeon(self):
        """副本匹配不做职业搭配，五个输出没治疗进本就灭"""
        obj = DungeonSystem()
        result = obj.match_dungeon()
        self.assertIsNotNone(result)

    def test_scale_difficulty(self):
        """难度缩放只加血量，不加减伤和伤害"""
        obj = DungeonSystem()
        result = obj.scale_difficulty()
        self.assertIsNotNone(result)

    def test_update_boss_phase(self):
        """BOSS阶段不做转换条件，血量到了不转阶段"""
        obj = DungeonSystem()
        result = obj.update_boss_phase()
        self.assertIsNotNone(result)

    def test_roll_loot(self):
        """掉落ROLL不做需求优先级，所有人都能需求"""
        obj = DungeonSystem()
        result = obj.roll_loot()
        self.assertIsNotNone(result)

    def test_update_dungeon_timer(self):
        """副本计时不做暂停，掉线了时间还在走"""
        obj = DungeonSystem()
        result = obj.update_dungeon_timer()
        self.assertIsNotNone(result)

