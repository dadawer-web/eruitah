; 捕获类似 @app.get 或 @router.post 的装饰器
; FastAPI/Flask 模式: @app.get("/path") 或 @router.post("/path/{id}")
; attribute 节点的字段: object (app/router) 和 attribute (get/post)
(decorated_definition
  (decorator
    (call
      function: (attribute
        attribute: (identifier) @http_method
      )
    )
  )
  definition: (function_definition
    name: (identifier) @function_name
  )
) @api_route
