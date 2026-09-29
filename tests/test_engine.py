"""副本测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import DungeonSystem, DungeonRun

class TestDifficulty:
    def test_difficulty_affects_hp(self):
        ds = DungeonSystem()
        normal = ds.apply_difficulty(1000, "normal")
        hard = ds.apply_difficulty(1000, "hard")
        assert hard > normal, "难度未影响怪物属性"

class TestScore:
    def test_score_considers_deaths(self):
        ds = DungeonSystem()
        ds.runs["r1"] = DungeonRun("r1", "normal", ["p1"], 0, deaths=0)
        ds.runs["r2"] = DungeonRun("r2", "normal", ["p1"], 0, deaths=10)
        s1 = ds.calc_score("r1")
        s2 = ds.calc_score("r2")
        assert s1 > s2, "评分未考虑死亡次数"
