; 捕获 Spring Boot 的 @GetMapping, @PostMapping 等
; 注: tree-sitter-java 中带参数的注解是 annotation，无参数的是 marker_annotation
(method_declaration
  (modifiers
    (annotation
      name: (identifier) @annotation_name
    )
  )
  name: (identifier) @method_name
) @api_route

; 同时捕获 marker_annotation (无参数注解如 @GetMapping("/path") 在某些版本中)
(method_declaration
  (modifiers
    (marker_annotation
      name: (identifier) @annotation_name
    )
  )
  name: (identifier) @method_name
) @api_route
