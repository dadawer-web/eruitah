package com.monopoly.model;

import java.util.Random;

/**
 * 不幸单元格
 */
public class UnluckyCell extends Cell {
    public UnluckyCell(int id, String name) {
        super(id, name, CellType.UNLUCKY);
    }
    
    @Override
    public void action(Player player) {
        Random random = new Random();
        int unluckyType = random.nextInt(3); // 0: 监狱, 1: 医院, 2: 税务局
        
        switch (unluckyType) {
            case 0:
                // 进监狱
                player.setInJail(true);
                player.setJailTurns(2); // 轮空两圈（包括当前回合）
                System.out.println(player.getName() + " 进入监狱，轮空两圈！");
                break;
            case 1:
                // 进医院
                player.setInHospital(true);
                player.setHospitalTurns(2);
                int hospitalFee = 500;
                player.payMoney(hospitalFee);
                System.out.println(player.getName() + " 进入医院，轮空两圈并支付医疗费: " + hospitalFee);
                break;
            case 2:
                // 税务局
                int taxAmount = (int)(player.getMoney() * 0.1); // 收取10%现金
                if (taxAmount < 100) taxAmount = 100; // 最低100
                player.payMoney(taxAmount);
                System.out.println(player.getName() + " 被税务局征税: " + taxAmount);
                break;
        }
    }
}