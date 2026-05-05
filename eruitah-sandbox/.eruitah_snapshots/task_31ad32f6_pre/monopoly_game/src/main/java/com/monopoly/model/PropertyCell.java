package com.monopoly.model;

/**
 * 房产单元格
 */
public class PropertyCell extends Cell {
    private int basePrice;
    private int baseRent;
    private int upgradeCost;
    private int level; // 0-3级，0表示未升级
    private Player owner;
    
    public PropertyCell(int id, String name, int basePrice, int baseRent, int upgradeCost) {
        super(id, name, CellType.PROPERTY);
        this.basePrice = basePrice;
        this.baseRent = baseRent;
        this.upgradeCost = upgradeCost;
        this.level = 0;
        this.owner = null;
    }
    
    @Override
    public void action(Player player) {
        if (owner == null) {
            // 无人拥有，可以购买
            System.out.println(player.getName() + " 停在未拥有的房产 " + getName());
        } else if (owner.equals(player)) {
            // 自己的房产，可以选择升级
            System.out.println(player.getName() + " 停在自己的房产 " + getName() + "，当前等级: " + level);
        } else {
            // 别人的房产，需要支付租金
            int rent = calculateRent();
            System.out.println(player.getName() + " 停在 " + owner.getName() + " 的房产 " + getName() + 
                             "，需要支付租金: " + rent);
            player.payMoney(rent);
            owner.receiveMoney(rent);
        }
    }
    
    public int calculateRent() {
        return baseRent * (level + 1); // 每升级一级，租金翻倍
    }
    
    public boolean canUpgrade(Player player) {
        return owner != null && owner.equals(player) && level < 3 && player.getMoney() >= upgradeCost;
    }
    
    public void upgrade() {
        if (level < 3) {
            level++;
            // 升级费用将在服务层扣除
        }
    }
    
    // Getters and Setters
    public int getBasePrice() { return basePrice; }
    public void setBasePrice(int basePrice) { this.basePrice = basePrice; }
    public int getBaseRent() { return baseRent; }
    public void setBaseRent(int baseRent) { this.baseRent = baseRent; }
    public int getUpgradeCost() { return upgradeCost; }
    public void setUpgradeCost(int upgradeCost) { this.upgradeCost = upgradeCost; }
    public int getLevel() { return level; }
    public void setLevel(int level) { this.level = level; }
    public Player getOwner() { return owner; }
    public void setOwner(Player owner) { this.owner = owner; }
}