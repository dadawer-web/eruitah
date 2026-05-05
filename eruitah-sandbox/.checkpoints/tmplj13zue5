#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
大富翁游戏 - 单机版实现
功能：至少4个玩家，包含AI玩家，支持地图文件存储，保存/加载游戏进度
"""

import random
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

class CellType(Enum):
    """地图单元格类型"""
    EMPTY = "empty"        # 空地，可以购买
    PROPERTY = "property"  # 房产
    CHANCE = "chance"      # 幸运/机会
    CARD = "card"          # 事件卡
    JAIL = "jail"          # 监狱
    HOSPITAL = "hospital"  # 医院
    TAX = "tax"            # 税收
    GO = "go"              # 起点
    GO_TO_JAIL = "go_to_jail"  # 直接进监狱
    FREE_PARKING = "free_parking"  # 免费停车

@dataclass
class Property:
    """房产信息"""
    name: str
    price: int
    rent: int
    owner: Optional[str] = None
    level: int = 0  # 等级（0=未升级，1=一级，2=二级等）
    
    def upgrade_cost(self) -> int:
        """升级成本"""
        return self.price // 2
    
    def get_rent(self) -> int:
        """获取当前租金"""
        if self.level == 0:
            return self.rent
        elif self.level == 1:
            return self.rent * 2
        elif self.level == 2:
            return self.rent * 3
        else:
            return self.rent * 4

@dataclass
class GameCell:
    """地图单元格"""
    id: int
    name: str
    cell_type: CellType
    property_info: Optional[Property] = None
    description: str = ""
    
    def __post_init__(self):
        if self.cell_type == CellType.PROPERTY and self.property_info is None:
            raise ValueError("Property type must have property_info")

@dataclass
class Player:
    """玩家信息"""
    def __init__(self, name: str, money: int = 1500, position: int = 0, in_jail: bool = False, jail_turns: int = 0, owned_properties: List[Property] = None, is_ai: bool = False, avatar: str = "👤"):
        self.name = name
        self.money = money
        self.position = position
        self.in_jail = in_jail
        self.jail_turns = jail_turns
        self.owned_properties = owned_properties if owned_properties is not None else []
        self.is_ai = is_ai
        self.avatar = avatar
    
    def bankrupt(self) -> bool:
        """检查是否破产"""
        return self.money < 0
    
    def add_money(self, amount: int):
        """增加资金"""
        self.money += amount
    
    def subtract_money(self, amount: int):
        """减少资金"""
        self.money -= amount
    
    def buy_property(self, property_obj: Property):
        """购买房产"""
        if self.money >= property_obj.price:
            self.money -= property_obj.price
            property_obj.owner = self.name
            self.owned_properties.append(property_obj)
            return True
        return False
    
    def sell_property(self, property_obj: Property, sell_price: int):
        """出售房产"""
        if property_obj in self.owned_properties:
            self.money += sell_price
            self.owned_properties.remove(property_obj)
            property_obj.owner = None
            return True
        return False

    def get_ai_move(self, game: 'Game') -> str:
        """AI玩家的决策逻辑"""
        # 简单的AI策略：优先购买便宜的房产，然后升级已有房产，最后尝试购买更多房产
        if self.bankrupt():
            return "pass"
        
        # 获取所有可购买的房产
        available_properties = []
        for cell in game.map.cells:
            if cell.cell_type == CellType.PROPERTY and cell.property_info and cell.property_info.owner is None:
                available_properties.append(cell.property_info)
        
        # 如果有可购买的房产，优先购买
        if available_properties:
            # 选择最便宜的房产
            cheapest_property = min(available_properties, key=lambda x: x.price)
            if self.money >= cheapest_property.price:
                return f"buy {cheapest_property.name}"
        
        # 检查是否有可以升级的房产
        for prop in self.owned_properties:
            if prop.level < 3 and self.money >= prop.upgrade_cost():
                return f"upgrade {prop.name}"
        
        # 如果没有可操作的，随机移动
        return "move"
    """玩家信息"""
    name: str
    money: int = 1500
    position: int = 0
    in_jail: bool = False
    jail_turns: int = 0
    owned_properties: List[Property] = field(default_factory=list)
    is_ai: bool = False
    avatar: str = "👤"
    
    def bankrupt(self) -> bool:
        """检查是否破产"""
        return self.money < 0
    
    def add_money(self, amount: int):
        """增加资金"""
        self.money += amount
    
    def subtract_money(self, amount: int):
        """减少资金"""
        self.money -= amount
    
    def buy_property(self, property_obj: Property):
        """购买房产"""
        if self.money >= property_obj.price:
            self.money -= property_obj.price
            property_obj.owner = self.name
            self.owned_properties.append(property_obj)
            return True
        return False
    
    def sell_property(self, property_obj: Property, sell_price: int):
        """出售房产"""
        if property_obj in self.owned_properties:
            self.money += sell_price
            self.owned_properties.remove(property_obj)
            property_obj.owner = None
            return True
        return False

class Dice:
    """骰子类"""
    def roll(self) -> int:
        """掷骰子"""
        return random.randint(1, 6) + random.randint(1, 6)

class GameMap:
    """游戏地图"""
    def __init__(self, cells: List[GameCell]):
        self.cells = cells
        self.size = len(cells)
    
    def get_cell(self, position: int) -> GameCell:
        """获取指定位置的单元格"""
        return self.cells[position % self.size]
    
    def get_cell_by_name(self, name: str) -> Optional[GameCell]:
        """根据名称获取单元格"""
        for cell in self.cells:
            if cell.name == name:
                return cell
        return None

class Game:
    """大富翁游戏主类"""
    def __init__(self, players: List[Player], map_data: GameMap):
        self.players = players
        self.current_player_index = 0
        self.dice = Dice()
        self.map = map_data
        self.game_over = False
        self.winner: Optional[Player] = None
        
        # 初始化玩家位置
        for player in self.players:
            player.position = 0  # 起点
    
    def get_current_player(self) -> Player:
        """获取当前玩家"""
        return self.players[self.current_player_index]
    
    def next_player(self):
        """切换到下一个玩家"""
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
    
    def roll_dice(self) -> int:
        """掷骰子并返回步数"""
        return self.dice.roll()
    
    def move_player(self, steps: int):
        """移动玩家"""
        current_pos = self.get_current_player().position
        new_pos = current_pos + steps
        
        # 检查是否经过起点（如果经过则获得200元）
        if new_pos >= self.map.size:
            self.get_current_player().add_money(200)
            new_pos = new_pos % self.map.size
        
        self.get_current_player().position = new_pos
        
        # 处理特殊单元格效果
        cell = self.map.get_cell(new_pos)
        
        # 如果是监狱、医院、税务局等，执行相应效果
        if cell.cell_type == CellType.JAIL:
            self.get_current_player().in_jail = True
            self.get_current_player().jail_turns = 3
            print(f"{self.get_current_player().name} 进入监狱！")
            
        elif cell.cell_type == CellType.HOSPITAL:
            cost = 50
            if self.get_current_player().money >= cost:
                self.get_current_player().subtract_money(cost)
                print(f"{self.get_current_player().name} 进入医院，支付医疗费 {cost} 元")
            else:
                print(f"{self.get_current_player().name} 无法支付医疗费，破产！")
                self.get_current_player().bankrupt()
                
        elif cell.cell_type == CellType.TAX:
            tax_rate = 0.1
            tax_amount = int(self.get_current_player().money * tax_rate)
            if tax_amount > 0:
                self.get_current_player().subtract_money(tax_amount)
                print(f"{self.get_current_player().name} 缴纳所得税 {tax_amount} 元")
        
        # 处理房产相关
        if cell.cell_type == CellType.PROPERTY and cell.property_info:
            property_obj = cell.property_info
            if property_obj.owner and property_obj.owner != self.get_current_player().name:
                # 是别人的房产，支付租金
                rent = property_obj.get_rent()
                if self.get_current_player().money >= rent:
                    self.get_current_player().subtract_money(rent)
                    owner = next(p for p in self.players if p.name == property_obj.owner)
                    owner.add_money(rent)
                    print(f"{self.get_current_player().name} 支付 {rent} 元给 {property_obj.owner}")
                else:
                    print(f"{self.get_current_player().name} 无法支付租金，破产！")
                    self.get_current_player().bankrupt()
                    
            elif property_obj.owner == self.get_current_player().name:
                # 是自己的房产，可以选择升级
                pass
    
    def check_game_over(self) -> bool:
        """检查游戏是否结束"""
        alive_players = [p for p in self.players if not p.bankrupt()]
        if len(alive_players) <= 1:
            self.game_over = True
            if len(alive_players) == 1:
                self.winner = alive_players[0]
            return True
        return False
    
    def save_game(self, filename: str):
        """保存游戏状态"""
        game_state = {
            'players': [],
            'current_player_index': self.current_player_index,
            'game_over': self.game_over,
            'winner': self.winner.name if self.winner else None,
            'map_size': self.map.size,
            'cells': []
        }
        
        # 序列化玩家信息
        for player in self.players:
            player_data = {
                'name': player.name,
                'money': player.money,
                'position': player.position,
                'in_jail': player.in_jail,
                'jail_turns': player.jail_turns,
                'owned_properties': []
            }
            
            # 序列化房产
            for prop in player.owned_properties:
                prop_data = {
                    'name': prop.name,
                    'price': prop.price,
                    'rent': prop.rent,
                    'owner': prop.owner,
                    'level': prop.level
                }
                player_data['owned_properties'].append(prop_data)
            
            game_state['players'].append(player_data)
        
        # 序列化地图信息
        for cell in self.map.cells:
            cell_data = {
                'id': cell.id,
                'name': cell.name,
                'cell_type': cell.cell_type.value,
                'description': cell.description
            }
            
            if cell.property_info:
                prop_data = {
                    'name': cell.property_info.name,
                    'price': cell.property_info.price,
                    'rent': cell.property_info.rent,
                    'owner': cell.property_info.owner,
                    'level': cell.property_info.level
                }
                cell_data['property_info'] = prop_data
            
            game_state['cells'].append(cell_data)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(game_state, f, ensure_ascii=False, indent=2)
    
    def load_game(self, filename: str):
        """加载游戏状态"""
        if not os.path.exists(filename):
            raise FileNotFoundError(f"游戏存档文件 {filename} 不存在")
        
        with open(filename, 'r', encoding='utf-8') as f:
            game_state = json.load(f)
        
        # 重建玩家
        self.players = []
        for player_data in game_state['players']:
            player = Player(
                name=player_data['name'],
                money=player_data['money'],
                position=player_data['position'],
                in_jail=player_data['in_jail'],
                jail_turns=player_data['jail_turns'],
                is_ai=False,
                avatar="👤"
            )
            
            # 加载房产
            for prop_data in player_data['owned_properties']:
                prop = Property(
                    name=prop_data['name'],
                    price=prop_data['price'],
                    rent=prop_data['rent'],
                    owner=prop_data['owner'],
                    level=prop_data['level']
                )
                player.owned_properties.append(prop)
            
            self.players.append(player)
        
        # 重建地图
        self.map = GameMap([])
        for cell_data in game_state['cells']:
            cell_type = CellType(cell_data['cell_type'])
            property_info = None
            
            if 'property_info' in cell_data and cell_data['property_info']:
                prop_data = cell_data['property_info']
                property_info = Property(
                    name=prop_data['name'],
                    price=prop_data['price'],
                    rent=prop_data['rent'],
                    owner=prop_data['owner'],
                    level=prop_data['level']
                )
            
            cell = GameCell(
                id=cell_data['id'],
                name=cell_data['name'],
                cell_type=cell_type,
                property_info=property_info,
                description=cell_data.get('description', '')
            )
            self.map.cells.append(cell)
        
        self.current_player_index = game_state['current_player_index']
        self.game_over = game_state['game_over']
        self.winner = self.players[0] if game_state['winner'] and len(self.players) > 0 else None
        
        # 更新当前玩家位置
        for player in self.players:
            player.position = self.map.size - 1  # 重置为起点位置
    
    def display_board(self):
        """显示游戏板"""
        print("\n" + "="*50)
        print("         🎲 大富翁游戏 🎲")
        print("="*50)
        
        # 显示玩家信息
        print("\n玩家信息:")
        for i, player in enumerate(self.players):
            status = "✅" if not player.bankrupt() else "❌"
            jail_status = " 🚔" if player.in_jail else ""
            print(f"{i+1}. {player.avatar} {player.name}: ¥{player.money}{jail_status} ({status})")
        
        # 显示当前位置
        current_player = self.get_current_player()
        current_cell = self.map.get_cell(current_player.position)
        print(f"\n当前玩家: {current_player.name}")
        print(f"当前位置: {current_cell.name} ({current_player.position})")
        print(f"当前状态: {'在监狱中' if current_player.in_jail else '正常'}")
        
        # 显示地图概览（简化版）
        print("\n地图概览 (简化):")
        for i, cell in enumerate(self.map.cells[:12]):  # 显示前12个格子
            if i == current_player.position:
                print(f"[{i}] {cell.name} {cell.cell_type.value} → {current_player.name}")
            else:
                print(f"[{i}] {cell.name} {cell.cell_type.value}")
        
        print("-"*50)
    
    def get_current_player(self) -> Player:
        """获取当前玩家"""
        return self.players[self.current_player_index]
    
    def next_player(self):
        """切换到下一个玩家"""
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
    
    def roll_dice(self) -> int:
        """掷骰子并返回步数"""
        return self.dice.roll()
    
    def move_player(self, steps: int):
        """移动玩家"""
        current_pos = self.get_current_player().position
        new_pos = current_pos + steps
        
        # 检查是否经过起点（如果经过则获得200元）
        if new_pos >= self.map.size:
            self.get_current_player().add_money(200)
            new_pos = new_pos % self.map.size
        
        self.get_current_player().position = new_pos
        
        # 处理特殊单元格效果
        cell = self.map.get_cell(new_pos)
        
        # 如果是监狱、医院、税务局等，执行相应效果
        if cell.cell_type == CellType.JAIL:
            self.get_current_player().in_jail = True
            self.get_current_player().jail_turns = 3
            print(f"{self.get_current_player().name} 进入监狱！")
            
        elif cell.cell_type == CellType.HOSPITAL:
            cost = 50
            if self.get_current_player().money >= cost:
                self.get_current_player().subtract_money(cost)
                print(f"{self.get_current_player().name} 进入医院，支付医疗费 {cost} 元")
            else:
                print(f"{self.get_current_player().name} 无法支付医疗费，破产！")
                self.get_current_player().bankrupt()
                
        elif cell.cell_type == CellType.TAX:
            tax_rate = 0.1
            tax_amount = int(self.get_current_player().money * tax_rate)
            if tax_amount > 0:
                self.get_current_player().subtract_money(tax_amount)
                print(f"{self.get_current_player().name} 缴纳所得税 {tax_amount} 元")
        
        # 处理房产相关
        if cell.cell_type == CellType.PROPERTY and cell.property_info:
            property_obj = cell.property_info
            if property_obj.owner and property_obj.owner != self.get_current_player().name:
                # 是别人的房产，支付租金
                rent = property_obj.get_rent()
                if self.get_current_player().money >= rent:
                    self.get_current_player().subtract_money(rent)
                    owner = next(p for p in self.players if p.name == property_obj.owner)
                    owner.add_money(rent)
                    print(f"{self.get_current_player().name} 支付 {rent} 元给 {property_obj.owner}")
                else:
                    print(f"{self.get_current_player().name} 无法支付租金，破产！")
                    self.get_current_player().bankrupt()
                    
            elif property_obj.owner == self.get_current_player().name:
                # 是自己的房产，可以选择升级
                pass
    
    def check_game_over(self) -> bool:
        """检查游戏是否结束"""
        alive_players = [p for p in self.players if not p.bankrupt()]
        if len(alive_players) <= 1:
            self.game_over = True
            if len(alive_players) == 1:
                self.winner = alive_players[0]
            return True
        return False
    
    def save_game(self, filename: str):
        """保存游戏状态"""
        game_state = {
            'players': [],
            'current_player_index': self.current_player_index,
            'game_over': self.game_over,
            'winner': self.winner.name if self.winner else None,
            'map_size': self.map.size,
            'cells': []
        }
        
        # 序列化玩家信息
        for player in self.players:
            player_data = {
                'name': player.name,
                'money': player.money,
                'position': player.position,
                'in_jail': player.in_jail,
                'jail_turns': player.jail_turns,
                'owned_properties': []
            }
            
            # 序列化房产
            for prop in player.owned_properties:
                prop_data = {
                    'name': prop.name,
                    'price': prop.price,
                    'rent': prop.rent,
                    'owner': prop.owner,
                    'level': prop.level
                }
                player_data['owned_properties'].append(prop_data)
            
            game_state['players'].append(player_data)
        
        # 序列化地图信息
        for cell in self.map.cells:
            cell_data = {
                'id': cell.id,
                'name': cell.name,
                'cell_type': cell.cell_type.value,
                'description': cell.description
            }
            
            if cell.property_info:
                prop_data = {
                    'name': cell.property_info.name,
                    'price': cell.property_info.price,
                    'rent': cell.property_info.rent,
                    'owner': cell.property_info.owner,
                    'level': cell.property_info.level
                }
                cell_data['property_info'] = prop_data
            
            game_state['cells'].append(cell_data)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(game_state, f, ensure_ascii=False, indent=2)
    
    def load_game(self, filename: str):
        """加载游戏状态"""
        if not os.path.exists(filename):
            raise FileNotFoundError(f"游戏存档文件 {filename} 不存在")
        
        with open(filename, 'r', encoding='utf-8') as f:
            game_state = json.load(f)
        
        # 重建玩家
        self.players = []
        for player_data in game_state['players']:
            player = Player(
                name=player_data['name'],
                money=player_data['money'],
                position=player_data['position'],
                in_jail=player_data['in_jail'],
                jail_turns=player_data['jail_turns'],
                is_ai=False,
                avatar="👤"
            )
            
            # 加载房产
            for prop_data in player_data['owned_properties']:
                prop = Property(
                    name=prop_data['name'],
                    price=prop_data['price'],
                    rent=prop_data['rent'],
                    owner=prop_data['owner'],
                    level=prop_data['level']
                )
                player.owned_properties.append(prop)
            
            self.players.append(player)
        
        # 重建地图
        self.map = GameMap([])
        for cell_data in game_state['cells']:
            cell_type = CellType(cell_data['cell_type'])
            property_info = None
            
            if 'property_info' in cell_data and cell_data['property_info']:
                prop_data = cell_data['property_info']
                property_info = Property(
                    name=prop_data['name'],
                    price=prop_data['price'],
                    rent=prop_data['rent'],
                    owner=prop_data['owner'],
                    level=prop_data['level']
                )
            
            cell = GameCell(
                id=cell_data['id'],
                name=cell_data['name'],
                cell_type=cell_type,
                property_info=property_info,
                description=cell_data.get('description', '')
            )
            self.map.cells.append(cell)
        
        self.current_player_index = game_state['current_player_index']
        self.game_over = game_state['game_over']
        self.winner = self.players[0] if game_state['winner'] and len(self.players) > 0 else None
        
        # 更新当前玩家位置
        for player in self.players:
            player.position = self.map.size - 1  # 重置为起点位置
    
    def display_board(self):
        """显示游戏板"""
        print("\n" + "="*50)
        print("         🎲 大富翁游戏 🎲")
        print("="*50)
        
        # 显示玩家信息
        print("\n玩家信息:")
        for i, player in enumerate(self.players):
            status = "✅" if not player.bankrupt() else "❌"
            jail_status = " 🚔" if player.in_jail else ""
            print(f"{i+1}. {player.avatar} {player.name}: ¥{player.money}{jail_status} ({status})")
        
        # 显示当前位置
        current_player = self.get_current_player()
        current_cell = self.map.get_cell(current_player.position)
        print(f"\n当前玩家: {current_player.name}")
        print(f"当前位置: {current_cell.name} ({current_player.position})")
        print(f"当前状态: {'在监狱中' if current_player.in_jail else '正常'}")
        
        # 显示地图概览（简化版）
        print("\n地图概览 (简化):")
        for i, cell in enumerate(self.map.cells[:12]):  # 显示前12个格子
            if i == current_player.position:
                print(f"[{i}] {cell.name} {cell.cell_type.value} → {current_player.name}")
            else:
                print(f"[{i}] {cell.name} {cell.cell_type.value}")
        
        print("-"*50)