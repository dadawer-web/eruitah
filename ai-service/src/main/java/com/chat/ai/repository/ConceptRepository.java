package com.chat.ai.repository;

import com.chat.ai.model.graph.ConceptNode;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ConceptRepository extends Neo4jRepository<ConceptNode, String> {
}
