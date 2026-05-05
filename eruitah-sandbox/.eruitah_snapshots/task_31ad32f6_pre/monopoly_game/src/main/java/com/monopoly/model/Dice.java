package com.monopoly.model;

import java.util.Random;

/**
 * 骰子类
 */
public class Dice {
    private Random random;
    
    public Dice() {
        this.random = new Random();
    }
    
    /**
     * 投掷骰子，返回1-6的点数
     */
    public int roll() {
        return random.nextInt(6) + 1;
    }
    
    /**
     * 同时投掷两个骰子
     */
    public int rollTwo() {
        return roll() + roll();
    }
}
