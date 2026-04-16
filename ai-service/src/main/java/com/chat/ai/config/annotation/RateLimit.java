package com.chat.ai.config.annotation;

import com.chat.ai.config.aspect.RateLimitAspect;

import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(RateLimit.Container.class)
public @interface RateLimit {

    enum Dimension {
        GLOBAL,
        IP,
        USER
    }

    Dimension dimension() default Dimension.GLOBAL;

    double count();

    long interval() default 1;

    TimeUnit timeUnit() default TimeUnit.SECONDS;

    long timeout() default 0;

    String fallback() default "";

    enum TimeUnit {
        MILLISECONDS, SECONDS, MINUTES, HOURS, DAYS
    }

    @Target(ElementType.METHOD)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Container {
        RateLimit[] value();
    }
}
