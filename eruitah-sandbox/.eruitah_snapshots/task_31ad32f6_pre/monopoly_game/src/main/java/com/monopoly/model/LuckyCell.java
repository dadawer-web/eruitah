package com.monopoly.model;

import java.util.Random;

/**
 * 幸运单元格
 */
public class LuckyCell extends Cell {
    private int reward;
    
    public LuckyCell(int id, String name, int reward) {
        super(id, name, CellType.LUCKY);
        this.reward = reward;
    }
    
    @Override
    public void action(Player player) {
        // 给予奖励
        player.receiveMoney(reward);
        System.out.println(player.getName() + " 停在幸运格 " + getName() + "，获得奖励: " + reward);
        
        // 有一定概率可以再投一次骰子
        Random random = new Random();
        if (random.nextInt(100) < 30) { // 30%概率再投一次
            player.setExtraTurn(true);
            System.out.println(player.getName() + " 获得额外投骰子机会！");
        }
    }
    
    public int getReward() { return reward; }
    public void setReward(int reward) { this.reward = reward; }
}