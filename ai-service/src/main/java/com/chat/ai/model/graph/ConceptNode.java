package com.chat.ai.model.graph;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Node("Concept")
public class ConceptNode {

    @Id
    private String name;

    private String subject;

    private Double difficulty;

    private String description;

    @Relationship(type = "PREREQUISITE_FOR", direction = Relationship.Direction.OUTGOING)
    @Builder.Default
    private Set<ConceptNode> prerequisites = new HashSet<>();
}
