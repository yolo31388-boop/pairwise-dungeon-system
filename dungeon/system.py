"""
pairwise-dungeon-system - DungeonSystem

副本系统核心：组队匹配、难度缩放、BOSS 阶段、掉落 ROLL、副本计时。
"""

import random
import time


# 5 人本标准配置：1 坦克 / 1 治疗 / 3 输出
TEAM_COMPOSITION = {"tank": 1, "healer": 1, "dps": 3}
TEAM_SIZE = sum(TEAM_COMPOSITION.values())
# 同队允许的最大装等差，避免萌新和大佬排一起
MAX_ITEM_LEVEL_GAP = 30
# 匹配超时（秒）：排不到人不会永远等
MATCH_TIMEOUT_SECONDS = 300.0

# 难度缩放为线性：每级固定增量，难度 1 和难度 10 是等差关系
HP_PER_LEVEL = 0.20        # 每级血量 +20%
DAMAGE_PER_LEVEL = 0.15    # 每级伤害 +15%
DR_PER_LEVEL = 0.02        # 每级减伤 +2%
MAX_DAMAGE_REDUCTION = 0.60
# 玩家数量补偿：以 5 人为基准，每多/少一人血量 +-20%、伤害 +-5%
BASE_PARTY_SIZE = 5
PLAYER_HP_FACTOR = 0.20
PLAYER_DAMAGE_FACTOR = 0.05

# BOSS 阶段：血量比例 <= threshold 时进入对应阶段，各阶段技能不同
BOSS_PHASES = [
    {"phase": 1, "hp_threshold": 1.00, "skills": ["cleave", "summon_adds"]},
    {"phase": 2, "hp_threshold": 0.60, "skills": ["cleave", "flame_breath", "charge"]},
    {"phase": 3, "hp_threshold": 0.30, "skills": ["enrage", "flame_breath", "meteor"]},
]
# 转场动画：转阶段期间播放，BOSS 无敌，不直接跳变
PHASE_TRANSITION = {
    "animation": "boss_roar_transition",
    "duration": 3.0,
    "invulnerable": True,
}

# 掉落 ROLL：需求 > 贪婪 > 放弃
ROLL_PRIORITY = {"need": 2, "greed": 1, "pass": 0}
ROLL_MIN = 1
ROLL_MAX = 100
# ROLL 错装备后的可交易窗口（秒）
LOOT_TRADE_WINDOW = 120.0

# 副本速通奖励档位（通关秒数，越快奖励越好）
SPEEDRUN_TIERS = (
    ("gold", 900.0),
    ("silver", 1500.0),
    ("bronze", 2400.0),
)


class DungeonSystem:
    def __init__(self):
        self.state = {}

    # ------------------------------------------------------------------
    # 副本匹配：职业搭配 + 装等检查 + 超时
    # ------------------------------------------------------------------
    def match_dungeon(self, players=None, dungeon=None, now=None):
        """匹配副本。

        players: [{"name", "role", "item_level", "queued_at"}]
        dungeon: {"min_item_level"} 副本装等门槛
        返回 {"teams", "waiting", "undergeared", "timed_out"}。
        """
        now = time.time() if now is None else now
        min_item_level = (dungeon or {}).get("min_item_level", 0)

        queue = self.state.setdefault("match_queue", [])
        if players:
            queue.extend(dict(player) for player in players)

        # 超时检查：排队太久的玩家移出队列，不再永远等
        timed_out = []
        active_queue = []
        for player in queue:
            queued_at = player.get("queued_at", now)
            if now - queued_at >= MATCH_TIMEOUT_SECONDS:
                timed_out.append(player)
            else:
                active_queue.append(player)
        queue[:] = active_queue

        # 装等检查：低于门槛的萌新不能进高难度本
        eligible, undergeared = [], []
        for player in queue:
            target = eligible if player.get("item_level", 0) >= min_item_level else undergeared
            target.append(player)

        # 职业搭配：按 1 坦 1 奶 3 输出组队，且同队装等差不能过大
        teams = []
        waiting = list(eligible)
        while len(waiting) >= TEAM_SIZE:
            team = self._build_team(waiting)
            if team is None:
                break
            teams.append(team)
            team_ids = {id(member) for member in team}
            waiting = [player for player in waiting if id(player) not in team_ids]

        queue[:] = waiting + undergeared
        return {
            "teams": teams,
            "waiting": waiting,
            "undergeared": undergeared,
            "timed_out": timed_out,
        }

    @staticmethod
    def _build_team(candidates):
        """从候选玩家中按职业配置组一支队，组不齐返回 None。"""
        team = []
        for role, count in TEAM_COMPOSITION.items():
            for _ in range(count):
                team_ids = {id(member) for member in team}
                pool = [
                    player for player in candidates
                    if player.get("role") == role and id(player) not in team_ids
                ]
                teammate = DungeonSystem._pick_teammate(pool, team)
                if teammate is None:
                    return None
                team.append(teammate)
        return team

    @staticmethod
    def _pick_teammate(pool, team):
        """装等检查：候选人与队内成员装等差不超过 MAX_ITEM_LEVEL_GAP。"""
        for player in pool:
            level = player.get("item_level", 0)
            if all(abs(level - member.get("item_level", 0)) <= MAX_ITEM_LEVEL_GAP
                   for member in team):
                return player
        return None

    # ------------------------------------------------------------------
    # 难度缩放：血量/伤害/减伤线性缩放 + 玩家数量补偿
    # ------------------------------------------------------------------
    def scale_difficulty(self, base_stats=None, level=1, player_count=BASE_PARTY_SIZE):
        """按难度等级和进本人数缩放 BOSS 属性。

        base_stats: {"hp", "damage", "damage_reduction"}
        返回缩放后的属性字典。
        """
        stats = {"hp": 1000.0, "damage": 100.0, "damage_reduction": 0.0}
        if base_stats:
            stats.update(base_stats)

        level = max(1, int(level))
        player_count = max(1, int(player_count))

        # 线性缩放：每一级都是固定增量，不存在难度 1 和 10 跨度失控
        steps = level - 1
        hp_scale = 1.0 + HP_PER_LEVEL * steps
        damage_scale = 1.0 + DAMAGE_PER_LEVEL * steps
        damage_reduction = min(
            MAX_DAMAGE_REDUCTION,
            stats["damage_reduction"] + DR_PER_LEVEL * steps,
        )

        # 玩家数量补偿：单人进本 BOSS 被削弱，满员进本 BOSS 更强
        player_delta = player_count - BASE_PARTY_SIZE
        hp_scale *= 1.0 + PLAYER_HP_FACTOR * player_delta
        damage_scale *= max(0.1, 1.0 + PLAYER_DAMAGE_FACTOR * player_delta)

        scaled = {
            "level": level,
            "player_count": player_count,
            "hp": stats["hp"] * hp_scale,
            "damage": stats["damage"] * damage_scale,
            "damage_reduction": damage_reduction,
        }
        self.state["scaled_difficulty"] = scaled
        return scaled

    # ------------------------------------------------------------------
    # BOSS 阶段：血量转换条件 + 阶段技能 + 转场动画
    # ------------------------------------------------------------------
    def update_boss_phase(self, boss=None):
        """根据当前血量更新 BOSS 阶段。

        boss: {"name", "current_hp", "max_hp", "phase"}
        返回 {"phase", "skills", "transition", "boss"}。
        """
        boss = dict(boss or self.state.get("boss") or {
            "name": "boss",
            "current_hp": 1000.0,
            "max_hp": 1000.0,
            "phase": 1,
        })
        max_hp = max(1.0, boss.get("max_hp", 1.0))
        hp_ratio = max(0.0, boss.get("current_hp", max_hp)) / max_hp

        # 转换条件：血量掉到阈值才进入下一阶段
        target_phase = BOSS_PHASES[0]
        for phase_def in BOSS_PHASES:
            if hp_ratio <= phase_def["hp_threshold"]:
                target_phase = phase_def

        old_phase = boss.get("phase", 1)
        transition = None
        if target_phase["phase"] != old_phase:
            # 转场动画：不直接跳变，转换期间 BOSS 无敌
            transition = dict(PHASE_TRANSITION)
            transition["from_phase"] = old_phase
            transition["to_phase"] = target_phase["phase"]

        boss["phase"] = target_phase["phase"]
        boss["skills"] = list(target_phase["skills"])
        boss["invulnerable"] = transition is not None
        self.state["boss"] = boss

        return {
            "phase": boss["phase"],
            "skills": boss["skills"],
            "transition": transition,
            "boss": boss,
        }

    # ------------------------------------------------------------------
    # 掉落 ROLL：需求优先级 + 点数验证 + 交易
    # ------------------------------------------------------------------
    def roll_loot(self, item=None, rollers=None, now=None):
        """ROLL 点分配掉落。

        item: {"name", "classes"}，classes 为可需求职业，空表示无限制
        rollers: [{"name", "class", "choice", "roll"}]
                 choice 取 "need"/"greed"/"pass"，roll 可省略（随机 1-100）
        返回 ROLL 点结果，含胜者和交易窗口。
        """
        now = time.time() if now is None else now
        item = dict(item or {"name": "loot", "classes": []})
        rollers = [dict(roller) for roller in (rollers or [])]
        allowed_classes = item.get("classes") or []

        results = []
        for roller in rollers:
            choice = roller.get("choice", "greed")
            # 需求优先级：不能装备的职业无权需求，自动降为贪婪
            if choice == "need" and allowed_classes and roller.get("class") not in allowed_classes:
                choice = "greed"
                roller["choice"] = choice
                roller["need_denied"] = True

            if choice == "pass":
                roller["roll"] = None
                roller["priority"] = ROLL_PRIORITY["pass"]
                results.append(roller)
                continue

            # 点数验证：ROLL 点必须是 1-100 的整数，非法值重新随机，杜绝必中 100
            roll = roller.get("roll")
            if not isinstance(roll, int) or isinstance(roll, bool) \
                    or not (ROLL_MIN <= roll <= ROLL_MAX):
                roll = random.randint(ROLL_MIN, ROLL_MAX)
            roller["roll"] = roll
            roller["priority"] = ROLL_PRIORITY.get(choice, ROLL_PRIORITY["greed"])
            results.append(roller)

        contenders = [roller for roller in results if roller.get("roll") is not None]
        # 先比需求优先级，同优先级再比点数
        winner = max(contenders, key=lambda roller: (roller["priority"], roller["roll"]),
                     default=None)

        record = {
            "item": item,
            "rolls": results,
            "winner": winner["name"] if winner else None,
            "won_at": now if winner else None,
            "trade_deadline": now + LOOT_TRADE_WINDOW if winner else None,
        }
        self.state.setdefault("loot_history", []).append(record)
        self.state["last_loot"] = record
        return record

    def trade_loot(self, item_name, from_player, to_player, now=None):
        """ROLL 错了可以在交易窗口内，把装备交易给同场 ROLL 过的队友。"""
        now = time.time() if now is None else now
        record = self.state.get("last_loot")
        if not record or record["item"].get("name") != item_name:
            return {"traded": False, "reason": "no_such_loot"}
        if record.get("winner") != from_player:
            return {"traded": False, "reason": "not_owner"}
        if now > record.get("trade_deadline", 0):
            return {"traded": False, "reason": "trade_window_expired"}
        eligible = {roller["name"] for roller in record["rolls"]
                    if roller.get("roll") is not None}
        if to_player not in eligible:
            return {"traded": False, "reason": "not_eligible"}

        record["winner"] = to_player
        record["traded_from"] = from_player
        return {"traded": True, "item": item_name, "from": from_player, "to": to_player}

    # ------------------------------------------------------------------
    # 副本计时：暂停 + 速通奖励 + 历史最快记录
    # ------------------------------------------------------------------
    def update_dungeon_timer(self, run=None, event="tick", now=None):
        """更新副本计时。

        run: {"dungeon", "elapsed", "paused", "finished", "last_tick"}
        event: "tick"/"pause"/"resume"/"finish"（掉线时传 "pause"）
        返回当前计时状态，通关时附带速通档位和最快记录。
        """
        now = time.time() if now is None else now
        run = dict(run or self.state.get("timer") or {
            "dungeon": "default",
            "elapsed": 0.0,
            "paused": False,
            "finished": False,
            "last_tick": now,
        })

        # 暂停或已通关时不累计时间：掉线了时间不会继续走
        if not run.get("paused") and not run.get("finished"):
            run["elapsed"] = run.get("elapsed", 0.0) + max(0.0, now - run.get("last_tick", now))
        run["last_tick"] = now

        if event == "pause":
            run["paused"] = True
        elif event == "resume":
            run["paused"] = False
        elif event == "finish":
            run["finished"] = True
            run["paused"] = False

        result = {
            "dungeon": run["dungeon"],
            "elapsed": run["elapsed"],
            "paused": run["paused"],
            "finished": run["finished"],
        }

        if run["finished"]:
            # 速通奖励：通关越快档位越高
            result["speedrun_tier"] = next(
                (tier for tier, limit in SPEEDRUN_TIERS if run["elapsed"] <= limit),
                None,
            )
            # 记录：保存历史成绩并维护最快通关时间
            records = self.state.setdefault(
                "speedrun_records", {}).setdefault(run["dungeon"], [])
            best_before = min(records) if records else None
            records.append(run["elapsed"])
            result["best_time"] = min(records)
            result["is_new_record"] = best_before is None or run["elapsed"] < best_before
            self.state.pop("timer", None)
        else:
            self.state["timer"] = run

        return result
