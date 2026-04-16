package com.chat.ai.repository;

import com.chat.ai.model.graph.QuestionNode;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface QuestionRepository extends Neo4jRepository<QuestionNode, String> {
}
