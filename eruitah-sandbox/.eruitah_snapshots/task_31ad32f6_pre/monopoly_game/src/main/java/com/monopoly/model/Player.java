package com.monopoly.model;

import java.util.ArrayList;
import java.util.List;

/**
 * 玩家类
 */
public class Player {
    private String name;
    private boolean isAI;
    private int money;
    private int position; // 当前位置（0-39）
    private boolean bankrupt; // 是否破产
    private boolean inJail; // 是否在监狱
    private int jailTurns; // 监狱剩余回合数
    private boolean inHospital; // 是否在医院
    private int hospitalTurns; // 医院剩余回合数
    private boolean extraTurn; // 是否有额外回合
    private List<PropertyCell> properties; // 拥有的房产
    
    public Player(String name, boolean isAI) {
        this.name = name;
        this.isAI = isAI;
        this.money = 15000; // 初始资金
        this.position = 0;
        this.bankrupt = false;
        this.inJail = false;
        this.jailTurns = 0;
        this.inHospital = false;
        this.hospitalTurns = 0;
        this.extraTurn = false;
        this.properties = new ArrayList<>();
    }
    
    public void move(int steps, int totalCells) {
        position = (position + steps) % totalCells;
        if (position == 0 && steps > 0) {
            // 经过起点，获得奖励
            receiveMoney(2000);
        }
    }
    
    public void payMoney(int amount) {
        money -= amount;
        if (money < 0) {
            bankrupt = true;
        }
    }
    
    public void receiveMoney(int amount) {
        money += amount;
    }
    
    public void addProperty(PropertyCell property) {
        properties.add(property);
        property.setOwner(this);
    }
    
    public boolean canBuyProperty(int price) {
        return money >= price;
    }
    
    public boolean canUpgradeProperty(int upgradeCost) {
        return money >= upgradeCost;
    }
    
    public void processStatus() {
        // 处理监狱状态
        if (inJail) {
            jailTurns--;
            if (jailTurns <= 0) {
                inJail = false;
            }
        }
        
        // 处理医院状态
        if (inHospital) {
            hospitalTurns--;
            if (hospitalTurns <= 0) {
                inHospital = false;
            }
        }
    }
    
    // Getters and Setters
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public boolean isAI() { return isAI; }
    public void setAI(boolean AI) { isAI = AI; }
    public int getMoney() { return money; }
    public void setMoney(int money) { this.money = money; }
    public int getPosition() { return position; }
    public void setPosition(int position) { this.position = position; }
    public boolean isBankrupt() { return bankrupt; }
    public void setBankrupt(boolean bankrupt) { this.bankrupt = bankrupt; }
    public boolean isInJail() { return inJail; }
    public void setInJail(boolean inJail) { this.inJail = inJail; }
    public int getJailTurns() { return jailTurns; }
    public void setJailTurns(int jailTurns) { this.jailTurns = jailTurns; }
    public boolean isInHospital() { return inHospital; }
    public void setInHospital(boolean inHospital) { this.inHospital = inHospital; }
    public int getHospitalTurns() { return hospitalTurns; }
    public void setHospitalTurns(int hospitalTurns) { this.hospitalTurns = hospitalTurns; }
    public boolean isExtraTurn() { return extraTurn; }
    public void setExtraTurn(boolean extraTurn) { this.extraTurn = extraTurn; }
    public List<PropertyCell> getProperties() { return properties; }
    public void setProperties(List<PropertyCell> properties) { this.properties = properties; }
}