package com.chat.ai.model;

public record HarvestJudgment(
    boolean canHarvest,
    int score,
    String feedback
) {}
