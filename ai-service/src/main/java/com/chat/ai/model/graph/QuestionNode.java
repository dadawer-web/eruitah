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
@Node("Question")
public class QuestionNode {

    @Id
    private String questionId;

    private String subject;

    private String questionStem;

    private String standardAnswer;

    private String difficulty;

    @Relationship(type = "TESTS", direction = Relationship.Direction.OUTGOING)
    @Builder.Default
    private Set<ConceptNode> testedConcepts = new HashSet<>();
}
